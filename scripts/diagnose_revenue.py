"""
특정 업체/연도의 delivery_requests 원본 행을 직접 까서 매출 불일치 원인을
확인하는 1회성 진단 스크립트.

사용법: python -m scripts.diagnose_revenue "업체명" 2025
"""

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
