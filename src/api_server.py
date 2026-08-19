"""
FastAPI 백엔드.

인증/로그인 미들웨어는 추가하지 않음 (오픈 접근).
필요시 nginx에서 IP 제한 또는 basic auth 추가 가능.
"""

from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src import aggregations
from src.collect_data import run_weekly
from src.db import BackfillProgress, CollectionRun, Competitor, get_session, utcnow

app = FastAPI(title="Competitor Sales Dashboard API")

REFRESH_STATE = {"status": "idle", "started_at": None, "finished_at": None, "error_message": None}


def get_db():
    with get_session() as session:
        yield session


class CompetitorCreate(BaseModel):
    name: str
    is_self: bool = False


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/competitors")
def list_competitors(db=Depends(get_db)):
    rows = db.query(Competitor).filter_by(is_active=True).order_by(Competitor.created_at).all()
    return [{"name": r.name, "is_self": r.is_self} for r in rows]


@app.post("/api/competitors")
def add_competitor(body: CompetitorCreate, db=Depends(get_db)):
    existing = db.query(Competitor).filter_by(name=body.name).one_or_none()
    if existing:
        existing.is_active = True
        existing.is_self = body.is_self
        existing.deleted_at = None
    else:
        db.add(Competitor(name=body.name, is_self=body.is_self, is_active=True))
    return {"name": body.name, "is_self": body.is_self}


@app.delete("/api/competitors/{name}")
def delete_competitor(name: str, db=Depends(get_db)):
    competitor = db.query(Competitor).filter_by(name=name, is_active=True).one_or_none()
    if not competitor:
        raise HTTPException(status_code=404, detail="경쟁사를 찾을 수 없습니다")
    competitor.is_active = False
    competitor.deleted_at = utcnow()
    return {"name": name, "is_active": False}


def _active_company_names(db):
    return [c.name for c in db.query(Competitor).filter_by(is_active=True).all()]


def _resolve_companies(db, companies: Optional[str]):
    if companies:
        return [c.strip() for c in companies.split(",") if c.strip()]
    return _active_company_names(db)


def _run_refresh_job():
    REFRESH_STATE.update(status="running", started_at=utcnow(), finished_at=None, error_message=None)
    try:
        run_weekly()
        REFRESH_STATE.update(status="done", finished_at=utcnow())
    except Exception as exc:  # noqa: BLE001
        REFRESH_STATE.update(status="failed", finished_at=utcnow(), error_message=str(exc))


@app.post("/api/refresh")
def trigger_refresh(background_tasks: BackgroundTasks):
    if REFRESH_STATE["status"] == "running":
        return {"status": "already_running"}
    background_tasks.add_task(_run_refresh_job)
    return {"status": "started"}


@app.get("/api/refresh/status")
def refresh_status(db=Depends(get_db)):
    last_run = db.query(CollectionRun).order_by(CollectionRun.id.desc()).first()
    return {
        **REFRESH_STATE,
        "last_run": None
        if not last_run
        else {
            "started_at": last_run.started_at,
            "finished_at": last_run.finished_at,
            "rows_fetched": last_run.rows_fetched,
            "rows_upserted": last_run.rows_upserted,
            "status": last_run.status,
            "error_message": last_run.error_message,
        },
    }


@app.get("/api/backfill-status")
def backfill_status(db=Depends(get_db)):
    rows = db.query(BackfillProgress).order_by(BackfillProgress.target_year).all()
    total = len(rows)
    done = sum(1 for r in rows if r.status == "done")
    return {
        "total_years": total,
        "done_years": done,
        "years": [
            {
                "target_year": r.target_year,
                "status": r.status,
                "rows_fetched": r.rows_fetched,
                "error_message": r.error_message,
            }
            for r in rows
        ],
    }


@app.get("/api/dashboard-data")
def dashboard_data(
    companies: Optional[str] = None, period: str = "all", year: Optional[int] = None, db=Depends(get_db)
):
    company_list = _resolve_companies(db, companies)
    if not company_list:
        raise HTTPException(status_code=400, detail="등록된 경쟁사가 없습니다")

    monthly = aggregations.monthly_series(db, company_list)
    yearly = aggregations.yearly_totals(db, company_list)
    selected_year = year if year is not None else (max(yearly["years"]) if yearly["years"] else None)

    return {
        "companies": company_list,
        "kpi": aggregations.kpi(db, company_list),
        "monthly_series": monthly["series"],
        "months": monthly["months"],
        "yearly_totals": yearly["totals"],
        "years": yearly["years"],
        "category_totals": aggregations.category_totals(db, company_list),
        "market_share": aggregations.market_share(db, company_list, period=period),
        "top_institutions": aggregations.top_institutions(db, company_list),
        "top_products": aggregations.top_products(db, company_list),
        "unit_price_comparison": aggregations.unit_price_comparison(db, company_list),
        "selected_year": selected_year,
        "year_kpi": aggregations.kpi_by_year(db, company_list, selected_year) if selected_year else {},
        "year_top_institutions": aggregations.top_institutions_by_year(db, company_list, selected_year)
        if selected_year
        else {},
    }


@app.get("/api/unit-price")
def unit_price(product: Optional[str] = None, companies: Optional[str] = None, db=Depends(get_db)):
    company_list = _resolve_companies(db, companies)
    if not company_list:
        raise HTTPException(status_code=400, detail="등록된 경쟁사가 없습니다")
    return aggregations.unit_price_comparison(db, company_list, product=product)


@app.get("/")
def index():
    return FileResponse("static/competitor_dashboard.html")


# API 라우트 등록 이후, 나머지 정적 자산(css/js 등 추가 시 대비)을 /static에 마운트합니다.
app.mount("/static", StaticFiles(directory="static"), name="static")
