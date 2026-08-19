"""
조달청 나라장터종합쇼핑몰품목정보서비스 - 특정품목조달내역 목록조회
(getSpcifyPrdlstPrcureInfoList) 수집 스크립트.

실행 모드:
  --full-backfill                 : START_YEAR(현재연도-4) ~ 현재까지 전체 수집
  --full-backfill --daily-chunk   : backfill_progress 기준 미완료 연도 1개만 수집
  --weekly                        : 지난주 월~일 구간만 수집
  --mock                          : 실제 API 대신 내장 샘플 데이터로 upsert 로직 검증
                                     (SERVICE_KEY/BASE_URL 없이도 동작 확인 가능)

모든 모드는 DB upsert를 사용합니다 (dlvr_req_no + dlvr_req_chg_cha + prdct_idnt_no
조합이 같으면 UPDATE, 없으면 INSERT). 이 3개 조합이 실제 API의 자연키입니다.

이 오퍼레이션은 세부품명번호(dtilPrdctClsfcNo)로 직접 필터링이 가능해서, 전국
데이터를 다 받지 않고 경쟁사들이 활동하는 업종(DTL_PRDCT_NOS)만 조회합니다.
조회기간도 최대 12개월까지 허용되어 --full-backfill --daily-chunk가 연도 단위로
한 번에 처리됩니다.

주의: 참고문서(조달청 OpenAPI 참고자료)의 이 오퍼레이션 "요청/응답 메시지 예제"
섹션이 다른 오퍼레이션 것과 뒤섞여 있는 것으로 보여, 공식 "응답 메시지 명세" 표를
기준으로 FIELD_MAP을 작성했습니다. 실제 응답과 다르면(예: fetched=0이 계속
나오거나 필드가 비어있으면) 실제 응답을 보고 FIELD_MAP을 조정해야 합니다.
"""

import argparse
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from decimal import Decimal

import requests
from dotenv import load_dotenv
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from src.db import BackfillProgress, CollectionRun, Competitor, DeliveryRequest, engine, get_session, utcnow

load_dotenv()

# 조달청_나라장터종합쇼핑몰품목정보서비스 - 특정품목조달내역 목록조회
BASE_URL = os.getenv(
    "BASE_URL",
    "https://apis.data.go.kr/1230000/at/ShoppingMallPrdctInfoService/getSpcifyPrdlstPrcureInfoList",
)
SERVICE_KEY = os.getenv("SERVICE_KEY", "REPLACE_ME")

# 응답 필드명 -> DB 컬럼명 매핑 (참고문서 "응답 메시지 명세" 표 기준)
FIELD_MAP = {
    "cntrctDlvrReqDate": "dcisn_dt",  # 계약납품요구일자
    "cntrctDlvrReqNo": "dlvr_req_no",  # 계약납품요구번호
    "cntrctDlvrReqChgOrd": "dlvr_req_chg_cha",  # 변경차수
    "prdctIdntNo": "prdct_idnt_no",  # 물품식별번호 (자연키 일부)
    "prdctClsfcNoNm": "prdct_clsfc_nm",  # 품명(물품분류명)
    "dtilPrdctClsfcNoNm": "dtl_prdct_nm",  # 세부품명
    "dminsttNm": "dmnd_instt_nm",  # 수요기관명
    "corpNm": "corp_nm",  # 업체명
    "bizno": "corp_biz_no",  # 업체사업자등록번호
    "uprcCntrctNo": "contract_no",  # 단가계약번호
    "prdctAmt": "dlvr_amt",  # 금액
    "prdctQty": "dlvr_qty",  # 수량
}

_INT_FIELDS = {"dlvr_req_chg_cha", "prdct_idnt_no"}
_NUMERIC_FIELDS = {"dlvr_amt", "dlvr_qty"}

START_YEAR_OFFSET = 4  # 현재연도 - 4 = 5개년
MAX_RANGE_DAYS = 364  # API 조회기간 제한 (최대 12개월, 여유있게 364일)
PAGE_SIZE = 500
REQUEST_DELAY_SEC = 0.1

# 경쟁사들이 활동하는 세부품명번호(코드)로 좁혀서 전국 데이터를 다 받지 않도록 필터링.
# inqryPrdctDiv=2(세부품명 조회) + dtilPrdctClsfcNo로 요청하며, API가 한 번에
# 하나의 코드만 받으므로 코드 개수만큼 요청을 나눠서 호출합니다.
# 필요시 .env의 DTL_PRDCT_NOS(콤마 구분)로 덮어쓸 수 있습니다. 비워두면(빈 리스트)
# 필터 없이 전국 데이터를 그대로 받습니다.
DTL_PRDCT_NOS = [
    s.strip()
    for s in os.getenv("DTL_PRDCT_NOS", "4323300101,8111159801,4323290201").split(",")
    if s.strip()
]


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
            "prdct_idnt_no": 11111111,
            "prdct_clsfc_nm": "통신소프트웨어",
            "dtl_prdct_nm": "통신소프트웨어",
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
            "prdct_idnt_no": 22222222,
            "prdct_clsfc_nm": "패키지소프트웨어",
            "dtl_prdct_nm": "패키지소프트웨어개발및도입서비스",
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
            "prdct_idnt_no": 11111111,
            "prdct_clsfc_nm": "통신소프트웨어",
            "dtl_prdct_nm": "통신소프트웨어",
            "dmnd_instt_nm": "국립중앙도서관",
            "dlvr_amt": 1_260_000,  # 금액이 갱신된 케이스
            "dlvr_qty": 10,
            "raw_json": "{}",
        },
        {
            # 같은 세부품명, 다른 물품식별번호 (서로 다른 품목 - 유니크키 검증용)
            "dcisn_dt": date(2025, 3, 10),
            "corp_nm": "가나컴퍼니",
            "corp_biz_no": "111-11-11111",
            "contract_no": "C-2025-001",
            "dlvr_req_no": "D-2025-0001",
            "dlvr_req_chg_cha": 0,
            "prdct_idnt_no": 33333333,
            "prdct_clsfc_nm": "통신소프트웨어",
            "dtl_prdct_nm": "통신소프트웨어",
            "dmnd_instt_nm": "국립중앙도서관",
            "dlvr_amt": 480_000,
            "dlvr_qty": 4,
            "raw_json": "{}",
        },
    ]


def _chunk_date_range(date_from: date, date_to: date, max_days: int = MAX_RANGE_DAYS):
    """API 조회기간이 최대 12개월로 제한되어 있어 max_days 단위로 분할."""
    chunks = []
    cur = date_from
    while cur <= date_to:
        chunk_end = min(date_to, cur + timedelta(days=max_days - 1))
        chunks.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return chunks


def _normalize_row(item: dict):
    row = {FIELD_MAP[k]: v for k, v in item.items() if k in FIELD_MAP}
    for k in _INT_FIELDS:
        if row.get(k) not in (None, ""):
            row[k] = int(row[k])
    for k in _NUMERIC_FIELDS:
        if row.get(k) not in (None, ""):
            row[k] = Decimal(str(row[k]))
    if row.get("dcisn_dt"):
        row["dcisn_dt"] = datetime.strptime(str(row["dcisn_dt"]), "%Y%m%d").date()
    row["raw_json"] = json.dumps(item, ensure_ascii=False)
    return row


def _parse_api_response(text: str):
    """이 오퍼레이션은 Type=json을 보내도 XML로 응답하는 경우가 있어 둘 다 처리."""
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)["response"]

    root = ET.fromstring(stripped)
    header_el = root.find(".//header")
    result_code = header_el.findtext("resultCode") if header_el is not None else None
    result_msg = header_el.findtext("resultMsg") if header_el is not None else None

    item_list = [
        {child.tag: child.text for child in item_el} for item_el in root.findall(".//items/item")
    ]
    total_count_text = root.findtext(".//totalCount")
    total_count = int(total_count_text) if total_count_text else 0

    return {
        "header": {"resultCode": result_code, "resultMsg": result_msg},
        "body": {"items": {"item": item_list}, "totalCount": total_count},
    }


def _fetch_chunk(date_from: date, date_to: date, dtl_prdct_no: str = None):
    rows = []
    page_no = 1
    label = f"{date_from} ~ {date_to}" + (f" [{dtl_prdct_no}]" if dtl_prdct_no else "")
    print(f"  [fetch] {label} 조회 시작...", flush=True)
    while True:
        params = {
            "ServiceKey": SERVICE_KEY,
            "Type": "json",
            "inqryDiv": 1,
            "inqryBgnDate": date_from.strftime("%Y%m%d"),
            "inqryEndDate": date_to.strftime("%Y%m%d"),
            "pageNo": page_no,
            "numOfRows": PAGE_SIZE,
        }
        if dtl_prdct_no:
            params["inqryPrdctDiv"] = 2
            params["dtilPrdctClsfcNo"] = dtl_prdct_no
        response = requests.get(BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        try:
            data = _parse_api_response(response.text)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"API 응답 파싱 실패 (status={response.status_code}). "
                f"응답 원문(앞 1000자): {response.text[:1000]!r}"
            ) from exc

        header = data["header"]
        if header.get("resultCode") != "00":
            raise RuntimeError(f"API 오류: {header.get('resultCode')} {header.get('resultMsg')}")

        body = data["body"]
        items = body.get("items") or {}
        item_list = items.get("item") if isinstance(items, dict) else items
        if item_list is None:
            item_list = []
        elif isinstance(item_list, dict):
            item_list = [item_list]

        rows.extend(_normalize_row(item) for item in item_list)

        total_count = int(body.get("totalCount", 0) or 0)
        print(f"    페이지 {page_no} 조회 완료 ({len(rows)}/{total_count}건 누적)", flush=True)
        if not item_list or page_no * PAGE_SIZE >= total_count:
            break
        page_no += 1
        time.sleep(REQUEST_DELAY_SEC)
    return rows


def fetch_rows(date_from: date, date_to: date):
    if not DTL_PRDCT_NOS:
        raise RuntimeError(
            "DTL_PRDCT_NOS가 비어있습니다. 이 API는 세부품명번호(inqryPrdctDiv=2) 없이는 "
            "조회할 수 없으므로 .env의 DTL_PRDCT_NOS에 경쟁사 업종의 세부품명번호를 "
            "콤마로 구분해 넣어주세요."
        )
    rows = []
    chunks = _chunk_date_range(date_from, date_to)
    total_calls = len(chunks) * len(DTL_PRDCT_NOS)
    call_i = 0
    for dtl_prdct_no in DTL_PRDCT_NOS:
        for chunk_from, chunk_to in chunks:
            call_i += 1
            print(f"[fetch] {call_i}/{total_calls}", flush=True)
            rows.extend(_fetch_chunk(chunk_from, chunk_to, dtl_prdct_no=dtl_prdct_no))
            time.sleep(REQUEST_DELAY_SEC)
    return rows


def upsert_rows(session, rows):
    """dlvr_req_no + dlvr_req_chg_cha + prdct_idnt_no 기준 upsert."""
    if not rows:
        return 0

    insert_fn = postgresql_insert if engine.dialect.name == "postgresql" else sqlite_insert
    conflict_cols = ["dlvr_req_no", "dlvr_req_chg_cha", "prdct_idnt_no"]
    update_cols = [
        "dcisn_dt",
        "corp_nm",
        "corp_biz_no",
        "contract_no",
        "prdct_clsfc_nm",
        "dtl_prdct_nm",
        "dmnd_instt_nm",
        "dlvr_amt",
        "dlvr_qty",
        "raw_json",
        "collected_at",
    ]

    upserted = 0
    for row in rows:
        row = {**row, "collected_at": utcnow()}
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
    started_at = utcnow()
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
                    finished_at=utcnow(),
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
    current_year = utcnow().year
    start_year = current_year - START_YEAR_OFFSET
    with get_session() as session:
        existing_years = {b.target_year for b in session.query(BackfillProgress).all()}
        for year in range(start_year, current_year + 1):
            if year not in existing_years:
                session.add(BackfillProgress(target_year=year, status="pending"))


def run_full_backfill(daily_chunk: bool, mock: bool = False):
    ensure_backfill_progress_rows()
    current_year = utcnow().year
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
            progress.started_at = utcnow()

        date_from = date(year, 1, 1)
        date_to = date(year, 12, 31)
        try:
            fetched, upserted = run_collection(date_from, date_to, mock=mock)
            with get_session() as session:
                progress = session.query(BackfillProgress).filter_by(target_year=year).one()
                progress.status = "done"
                progress.rows_fetched = fetched
                progress.finished_at = utcnow()
            print(f"[backfill] {year}년 완료: fetched={fetched}, upserted={upserted}")
        except Exception as exc:  # noqa: BLE001
            with get_session() as session:
                progress = session.query(BackfillProgress).filter_by(target_year=year).one()
                progress.status = "failed"
                progress.error_message = str(exc)
                progress.finished_at = utcnow()
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
