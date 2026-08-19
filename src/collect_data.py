"""
공공데이터포털 "조달청_종합쇼핑몰 납품요구 물품 내역" API 수집 스크립트.

실행 모드:
  --full-backfill                 : START_YEAR(현재연도-4) ~ 현재까지 전체 수집
  --full-backfill --daily-chunk   : backfill_progress 기준 미완료 연도 1개만 수집
  --weekly                        : 지난주 월~일 구간만 수집
  --mock                          : 실제 API 대신 내장 샘플 데이터로 upsert 로직 검증
                                     (SERVICE_KEY/BASE_URL 없이도 동작 확인 가능)

모든 모드는 DB upsert를 사용합니다 (dlvr_req_no + dlvr_req_chg_cha +
prdct_clsfc_nm + dtl_prdct_nm 조합이 같으면 UPDATE, 없으면 INSERT).
"""

import argparse
import os
from datetime import date, datetime, timedelta

import requests
from dotenv import load_dotenv
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from src.db import BackfillProgress, CollectionRun, Competitor, DeliveryRequest, engine, get_session

load_dotenv()

# 조달청_나라장터종합쇼핑몰품목정보서비스 - 납품요구상세정보조회
BASE_URL = os.getenv(
    "BASE_URL",
    "https://apis.data.go.kr/1230000/at/ShoppingMallPrdctInfoService/getDlvrReqDtlInfoList",
)
SERVICE_KEY = os.getenv("SERVICE_KEY", "REPLACE_ME")

# TODO(Swagger 확인 필요): 응답 필드명을 확인해서 DB 컬럼명과의 매핑을 채우세요.
FIELD_MAP = {
    # "응답필드명": "db컬럼명",
    "dcisnDt": "dcisn_dt",
    "corpNm": "corp_nm",
    "corpBizNo": "corp_biz_no",
    "contractNo": "contract_no",
    "dlvrReqNo": "dlvr_req_no",
    "dlvrReqChgCha": "dlvr_req_chg_cha",
    "prdctClsfcNm": "prdct_clsfc_nm",
    "dtlPrdctNm": "dtl_prdct_nm",
    "dmndInsttNm": "dmnd_instt_nm",
    "dlvrAmt": "dlvr_amt",
    "dlvrQty": "dlvr_qty",
}

START_YEAR_OFFSET = 4  # 현재연도 - 4 = 5개년


def _mock_rows():
    """실 API 응답 대신 사용하는 샘플 데이터 (upsert 로직 검증용)."""
    return [
        {
            "dcisn_dt": date(2025, 3, 10),
            "corp_nm": "가나컴퍼니",
            "corp_biz_no": "111-11-11111",
            "contract_no": "C-2025-001",
            "dlvr_req_no": "D-2025-0001",
            "dlvr_req_chg_cha": 0,
            "prdct_clsfc_nm": "사무용가구",
            "dtl_prdct_nm": "사무용 의자",
            "dmnd_instt_nm": "국립중앙도서관",
            "dlvr_amt": 1_200_000,
            "dlvr_qty": 10,
            "raw_json": "{}",
        },
        {
            "dcisn_dt": date(2025, 3, 12),
            "corp_nm": "다라주식회사",
            "corp_biz_no": "222-22-22222",
            "contract_no": "C-2025-002",
            "dlvr_req_no": "D-2025-0002",
            "dlvr_req_chg_cha": 0,
            "prdct_clsfc_nm": "사무기기",
            "dtl_prdct_nm": "복합기",
            "dmnd_instt_nm": "서울특별시청",
            "dlvr_amt": 3_500_000,
            "dlvr_qty": 2,
            "raw_json": "{}",
        },
        {
            # 첫 번째 행의 변경차수 1건 (동일 키의 UPDATE 케이스 검증용)
            "dcisn_dt": date(2025, 3, 15),
            "corp_nm": "가나컴퍼니",
            "corp_biz_no": "111-11-11111",
            "contract_no": "C-2025-001",
            "dlvr_req_no": "D-2025-0001",
            "dlvr_req_chg_cha": 0,
            "prdct_clsfc_nm": "사무용가구",
            "dtl_prdct_nm": "사무용 의자",
            "dmnd_instt_nm": "국립중앙도서관",
            "dlvr_amt": 1_260_000,  # 금액이 갱신된 케이스
            "dlvr_qty": 10,
            "raw_json": "{}",
        },
    ]


def fetch_rows(date_from: date, date_to: date):
    """실제 API 호출. TODO(Swagger 확인 필요): 파라미터명/페이징 구조 확인 후 구현."""
    params = {
        "serviceKey": SERVICE_KEY,
        "dcisnDtFrom": date_from.strftime("%Y%m%d"),
        "dcisnDtTo": date_to.strftime("%Y%m%d"),
        # TODO: pageNo, numOfRows 등 실제 페이징 파라미터 추가
    }
    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    raw_items = response.json()  # TODO: 실제 응답 구조에 맞게 파싱

    rows = []
    for item in raw_items:
        row = {FIELD_MAP[k]: v for k, v in item.items() if k in FIELD_MAP}
        row["raw_json"] = str(item)
        rows.append(row)
    return rows


def upsert_rows(session, rows):
    """dlvr_req_no + dlvr_req_chg_cha + prdct_clsfc_nm + dtl_prdct_nm 기준 upsert."""
    if not rows:
        return 0

    insert_fn = postgresql_insert if engine.dialect.name == "postgresql" else sqlite_insert
    conflict_cols = ["dlvr_req_no", "dlvr_req_chg_cha", "prdct_clsfc_nm", "dtl_prdct_nm"]
    update_cols = [
        "dcisn_dt",
        "corp_nm",
        "corp_biz_no",
        "contract_no",
        "dmnd_instt_nm",
        "dlvr_amt",
        "dlvr_qty",
        "raw_json",
        "collected_at",
    ]

    upserted = 0
    for row in rows:
        row = {**row, "collected_at": datetime.utcnow()}
        stmt = insert_fn(DeliveryRequest).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_cols,
            set_={col: getattr(stmt.excluded, col) for col in update_cols},
        )
        session.execute(stmt)
        upserted += 1
    return upserted


def active_competitor_names(session):
    return [c.name for c in session.query(Competitor).filter_by(is_active=True).all()]


def run_collection(date_from: date, date_to: date, mock: bool = False):
    started_at = datetime.utcnow()
    status = "success"
    error_message = None
    rows_fetched = 0
    rows_upserted = 0

    try:
        with get_session() as session:
            competitor_names = active_competitor_names(session)
            if mock:
                rows = _mock_rows()
            else:
                rows = fetch_rows(date_from, date_to)

            # 경쟁사 목록이 등록되어 있으면 필터링 (API에 업체명 필터가 없으므로 코드에서 필터)
            if competitor_names:
                rows = [r for r in rows if r.get("corp_nm") in competitor_names]

            rows_fetched = len(rows)
            rows_upserted = upsert_rows(session, rows)
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        error_message = str(exc)
        raise
    finally:
        with get_session() as session:
            session.add(
                CollectionRun(
                    started_at=started_at,
                    finished_at=datetime.utcnow(),
                    date_from=date_from,
                    date_to=date_to,
                    rows_fetched=rows_fetched,
                    rows_upserted=rows_upserted,
                    status=status,
                    error_message=error_message,
                )
            )

    return rows_fetched, rows_upserted


def ensure_backfill_progress_rows():
    current_year = datetime.utcnow().year
    start_year = current_year - START_YEAR_OFFSET
    with get_session() as session:
        existing_years = {b.target_year for b in session.query(BackfillProgress).all()}
        for year in range(start_year, current_year + 1):
            if year not in existing_years:
                session.add(BackfillProgress(target_year=year, status="pending"))


def run_full_backfill(daily_chunk: bool, mock: bool = False):
    ensure_backfill_progress_rows()
    current_year = datetime.utcnow().year
    start_year = current_year - START_YEAR_OFFSET

    with get_session() as session:
        pending_years = [
            b.target_year
            for b in session.query(BackfillProgress)
            .filter(BackfillProgress.status.in_(["pending", "failed"]))
            .order_by(BackfillProgress.target_year)
            .all()
        ]

    years_to_run = pending_years[:1] if daily_chunk else list(range(start_year, current_year + 1))

    for year in years_to_run:
        with get_session() as session:
            progress = session.query(BackfillProgress).filter_by(target_year=year).one()
            progress.status = "in_progress"
            progress.started_at = datetime.utcnow()

        date_from = date(year, 1, 1)
        date_to = date(year, 12, 31)
        try:
            fetched, upserted = run_collection(date_from, date_to, mock=mock)
            with get_session() as session:
                progress = session.query(BackfillProgress).filter_by(target_year=year).one()
                progress.status = "done"
                progress.rows_fetched = fetched
                progress.finished_at = datetime.utcnow()
            print(f"[backfill] {year}년 완료: fetched={fetched}, upserted={upserted}")
        except Exception as exc:  # noqa: BLE001
            with get_session() as session:
                progress = session.query(BackfillProgress).filter_by(target_year=year).one()
                progress.status = "failed"
                progress.error_message = str(exc)
                progress.finished_at = datetime.utcnow()
            print(f"[backfill] {year}년 실패: {exc}")


def run_weekly(mock: bool = False):
    with get_session() as session:
        pending = (
            session.query(BackfillProgress)
            .filter(BackfillProgress.status.in_(["pending", "failed"]))
            .order_by(BackfillProgress.target_year)
            .all()
        )
        if pending:
            years = ", ".join(str(p.target_year) for p in pending)
            print(f"[weekly] 경고: 백필 미완료 연도가 있습니다: {years}")

    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    fetched, upserted = run_collection(last_monday, last_sunday, mock=mock)
    print(f"[weekly] {last_monday} ~ {last_sunday} 완료: fetched={fetched}, upserted={upserted}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-backfill", action="store_true")
    parser.add_argument("--daily-chunk", action="store_true")
    parser.add_argument("--weekly", action="store_true")
    parser.add_argument("--mock", action="store_true", help="실제 API 대신 샘플 데이터 사용")
    args = parser.parse_args()

    if args.full_backfill:
        run_full_backfill(daily_chunk=args.daily_chunk, mock=args.mock)
    elif args.weekly:
        run_weekly(mock=args.mock)
    else:
        parser.error("--full-backfill 또는 --weekly 중 하나를 지정하세요")


if __name__ == "__main__":
    main()
