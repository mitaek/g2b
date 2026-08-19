"""
대시보드용 집계 쿼리 모음.

DB 방언(SQLite/PostgreSQL)에 의존하지 않도록, delivery_requests를 조회한 뒤
파이썬에서 집계합니다. 소수 경쟁사 단위 집계라 데이터량 대비 무리 없는 접근입니다.
"""

from collections import defaultdict
from datetime import date, timedelta

from src.db import DeliveryRequest

TOP_N = 10


def _rows_for_companies(session, companies, date_from=None):
    query = session.query(DeliveryRequest).filter(DeliveryRequest.corp_nm.in_(companies))
    if date_from:
        query = query.filter(DeliveryRequest.dcisn_dt >= date_from)
    return query.all()


def _amt(row):
    return float(row.dlvr_amt or 0)


def _qty(row):
    return float(row.dlvr_qty or 0)


def _period_start(period: str):
    if period == "1y":
        return date.today() - timedelta(days=365)
    return None


def kpi(session, companies):
    rows = _rows_for_companies(session, companies)
    current_year = date.today().year
    result = {}
    for company in companies:
        crows = [r for r in rows if r.corp_nm == company]
        total = sum(_amt(r) for r in crows)
        this_year = sum(_amt(r) for r in crows if r.dcisn_dt and r.dcisn_dt.year == current_year)
        last_year = sum(_amt(r) for r in crows if r.dcisn_dt and r.dcisn_dt.year == current_year - 1)
        yoy = round((this_year - last_year) / last_year * 100, 1) if last_year else None
        result[company] = {
            "total_revenue": total,
            "recent_year_revenue": this_year,
            "yoy_growth_pct": yoy,
        }
    return result


def monthly_series(session, companies):
    rows = _rows_for_companies(session, companies)
    by_company_month = defaultdict(lambda: defaultdict(float))
    months = set()
    for r in rows:
        if not r.dcisn_dt:
            continue
        month_key = f"{r.dcisn_dt.year:04d}-{r.dcisn_dt.month:02d}"
        by_company_month[r.corp_nm][month_key] += _amt(r)
        months.add(month_key)

    sorted_months = sorted(months)
    series = {
        company: [by_company_month[company].get(m, 0.0) for m in sorted_months] for company in companies
    }
    return {"months": sorted_months, "series": series}


def yearly_totals(session, companies):
    rows = _rows_for_companies(session, companies)
    by_company_year = defaultdict(lambda: defaultdict(float))
    years = set()
    for r in rows:
        if not r.dcisn_dt:
            continue
        by_company_year[r.corp_nm][r.dcisn_dt.year] += _amt(r)
        years.add(r.dcisn_dt.year)

    sorted_years = sorted(years)
    totals = {
        company: [by_company_year[company].get(y, 0.0) for y in sorted_years] for company in companies
    }
    return {"years": sorted_years, "totals": totals}


def kpi_by_year(session, companies, year):
    rows = _rows_for_companies(session, companies)
    result = {}
    for company in companies:
        total = sum(
            _amt(r) for r in rows if r.corp_nm == company and r.dcisn_dt and r.dcisn_dt.year == year
        )
        result[company] = {"total_revenue": total}
    return result


def top_institutions_by_year(session, companies, year):
    rows = [r for r in _rows_for_companies(session, companies) if r.dcisn_dt and r.dcisn_dt.year == year]
    by_company_inst = defaultdict(lambda: defaultdict(lambda: {"revenue": 0.0, "count": 0}))
    for r in rows:
        inst = r.dmnd_instt_nm or "미상"
        entry = by_company_inst[r.corp_nm][inst]
        entry["revenue"] += _amt(r)
        entry["count"] += 1

    result = {}
    for company in companies:
        items = [
            {"institution": name, "revenue": v["revenue"], "count": v["count"]}
            for name, v in by_company_inst[company].items()
        ]
        items.sort(key=lambda x: x["revenue"], reverse=True)
        result[company] = items[:TOP_N]
    return result


def category_totals(session, companies):
    rows = _rows_for_companies(session, companies)
    result = {company: defaultdict(float) for company in companies}
    for r in rows:
        category = r.prdct_clsfc_nm or "미분류"
        result[r.corp_nm][category] += _amt(r)
    return {company: dict(cats) for company, cats in result.items()}


def market_share(session, companies, period="all"):
    rows = _rows_for_companies(session, companies, date_from=_period_start(period))
    totals = defaultdict(float)
    for r in rows:
        totals[r.corp_nm] += _amt(r)
    grand_total = sum(totals.values())
    if grand_total == 0:
        return {company: 0.0 for company in companies}
    return {company: round(totals.get(company, 0.0) / grand_total * 100, 1) for company in companies}


def top_institutions(session, companies):
    rows = _rows_for_companies(session, companies)
    by_company_inst = defaultdict(lambda: defaultdict(lambda: {"revenue": 0.0, "count": 0}))
    for r in rows:
        inst = r.dmnd_instt_nm or "미상"
        entry = by_company_inst[r.corp_nm][inst]
        entry["revenue"] += _amt(r)
        entry["count"] += 1

    result = {}
    for company in companies:
        items = [
            {"institution": name, "revenue": v["revenue"], "count": v["count"]}
            for name, v in by_company_inst[company].items()
        ]
        items.sort(key=lambda x: x["revenue"], reverse=True)
        result[company] = items[:TOP_N]
    return result


def top_products(session, companies):
    rows = _rows_for_companies(session, companies)
    by_company_product = defaultdict(
        lambda: defaultdict(lambda: {"category": None, "revenue": 0.0, "qty": 0.0})
    )
    for r in rows:
        name = r.dtl_prdct_nm or "미상"
        entry = by_company_product[r.corp_nm][name]
        entry["category"] = r.prdct_clsfc_nm
        entry["revenue"] += _amt(r)
        entry["qty"] += _qty(r)

    result = {}
    for company in companies:
        items = []
        for name, v in by_company_product[company].items():
            avg_unit_price = v["revenue"] / v["qty"] if v["qty"] else None
            items.append(
                {
                    "product": name,
                    "category": v["category"],
                    "revenue": v["revenue"],
                    "qty": v["qty"],
                    "avg_unit_price": avg_unit_price,
                }
            )
        items.sort(key=lambda x: x["revenue"], reverse=True)
        result[company] = items[:TOP_N]
    return result


def unit_price_comparison(session, companies, product=None):
    rows = _rows_for_companies(session, companies)
    by_product_company = defaultdict(lambda: defaultdict(lambda: {"revenue": 0.0, "qty": 0.0}))
    for r in rows:
        name = r.dtl_prdct_nm or "미상"
        entry = by_product_company[name][r.corp_nm]
        entry["revenue"] += _amt(r)
        entry["qty"] += _qty(r)

    if product:
        target_products = [product] if product in by_product_company else []
    else:
        # 공통 거래 품목(2개 이상 업체가 취급) 중 매출 상위 TOP_N 자동 선정
        common = [
            name
            for name, per_company in by_product_company.items()
            if len(per_company) >= 2
        ]
        common.sort(
            key=lambda name: sum(v["revenue"] for v in by_product_company[name].values()),
            reverse=True,
        )
        target_products = common[:TOP_N]

    result = {}
    for name in target_products:
        per_company = by_product_company[name]
        result[name] = {
            company: (per_company[company]["revenue"] / per_company[company]["qty"])
            if company in per_company and per_company[company]["qty"]
            else None
            for company in companies
        }
    return result
