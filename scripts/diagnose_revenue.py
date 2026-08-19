"""
특정 업체/연도의 delivery_requests 원본 행을 직접 까서 매출 불일치 원인을
확인하는 1회성 진단 스크립트.

사용법: python -m scripts.diagnose_revenue "업체명" 2025
"""

import json
import sys
from collections import defaultdict

from src.db import DeliveryRequest, get_session

company = sys.argv[1]
year = int(sys.argv[2])

with get_session() as session:
    rows = (
        session.query(DeliveryRequest)
        .filter(DeliveryRequest.corp_nm == company)
        .all()
    )
    rows = [r for r in rows if r.dcisn_dt and r.dcisn_dt.year == year]

    print(f"총 행 수: {len(rows)}")
    total_naive = sum(float(r.dlvr_amt or 0) for r in rows)
    print(f"단순 합계(현재 방식): {total_naive:,.0f}원")

    # dlvr_req_no + prdct_idnt_no 별로 chg_cha가 여러 개 있는지 확인
    groups = defaultdict(list)
    for r in rows:
        groups[(r.dlvr_req_no, r.prdct_idnt_no)].append(r)

    multi_revision_groups = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"동일 (납품요구번호, 물품식별번호) 조합인데 행이 2개 이상인 경우: {len(multi_revision_groups)}건")
    for (req_no, idnt_no), rs in list(multi_revision_groups.items())[:5]:
        print(f"  {req_no} / {idnt_no}: " + ", ".join(f"chg_cha={r.dlvr_req_chg_cha} amt={r.dlvr_amt}" for r in rs))

    # 최신 변경차수만 남기고 합산했을 때의 값
    total_dedup = 0.0
    for (req_no, idnt_no), rs in groups.items():
        latest = max(rs, key=lambda r: r.dlvr_req_chg_cha)
        total_dedup += float(latest.dlvr_amt or 0)
    print(f"(납품요구번호,물품식별번호)별 최신 변경차수만 합산: {total_dedup:,.0f}원")

    # collected_at 기준으로 언제 수집된 데이터인지 확인 (여러 시점에 걸쳐 있으면 재수집 전 잔여 데이터 의심)
    collected_times = sorted({r.collected_at.strftime("%Y-%m-%d %H:%M") for r in rows if r.collected_at})
    print(f"collected_at 종류: {collected_times[:10]}{' ...' if len(collected_times) > 10 else ''}")

    # 수요기관별 매출 top5 + 가장 금액이 큰 개별 행의 원본 API 응답(raw_json) 출력
    print("\n=== 수요기관별 매출 top5 ===")
    by_inst = defaultdict(lambda: {"revenue": 0.0, "count": 0, "rows": []})
    for r in rows:
        entry = by_inst[r.dmnd_instt_nm or "미상"]
        entry["revenue"] += float(r.dlvr_amt or 0)
        entry["count"] += 1
        entry["rows"].append(r)
    top_insts = sorted(by_inst.items(), key=lambda kv: kv[1]["revenue"], reverse=True)[:5]
    for inst, v in top_insts:
        print(f"{inst}: {v['revenue']:,.0f}원 ({v['count']}건)")

    print("\n=== 매출 top5 개별 행의 원본 API 응답 ===")
    top_rows = sorted(rows, key=lambda r: float(r.dlvr_amt or 0), reverse=True)[:5]
    for r in top_rows:
        print(
            f"- dlvr_req_no={r.dlvr_req_no} chg_cha={r.dlvr_req_chg_cha} "
            f"prdct_idnt_no={r.prdct_idnt_no} dcisn_dt={r.dcisn_dt} dlvr_amt={r.dlvr_amt} "
            f"dmnd_instt_nm={r.dmnd_instt_nm}"
        )
        print(f"  raw_json: {r.raw_json}")

    # cntrctDlvrDivNm(총액계약/납품요구) 구분별 합계 - 원 프로젝트 스펙은 "납품요구"만 대상
    print("\n=== cntrctDlvrDivNm(계약납품구분)별 합계 ===")
    by_div = defaultdict(lambda: {"revenue": 0.0, "count": 0})
    for r in rows:
        div = json.loads(r.raw_json).get("cntrctDlvrDivNm", "?")
        by_div[div]["revenue"] += float(r.dlvr_amt or 0)
        by_div[div]["count"] += 1
    for div, v in by_div.items():
        print(f"{div}: {v['revenue']:,.0f}원 ({v['count']}건)")

    only_dlvr_req_total = sum(
        float(r.dlvr_amt or 0) for r in rows if json.loads(r.raw_json).get("cntrctDlvrDivNm") == "납품요구"
    )
    print(f"\n'납품요구'만 합산: {only_dlvr_req_total:,.0f}원")
