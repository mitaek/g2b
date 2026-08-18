"""
공공데이터포털 "조달청_종합쇼핑몰 납품요구 물품 내역" API 수집 스크립트.

실행 모드 (2단계 이후 구현 예정):
  --full-backfill                 : START_YEAR(현재연도-4) ~ 현재까지 전체 수집
  --full-backfill --daily-chunk   : backfill_progress 기준 미완료 연도 1개만 수집
  --weekly                        : 지난주 월~일 구간만 수집

TODO(2단계): db.py의 세션/모델 연동, upsert 로직, collection_runs/backfill_progress 기록.
"""

from dotenv import load_dotenv

load_dotenv()

# TODO(Swagger 확인 필요): 공공데이터포털에서 실제 요청 주소를 확인해서 교체하세요.
# 예: https://apis.data.go.kr/1230000/ShoppingMallPrdlstInfoService/getDlvrReqInfoList
BASE_URL = "https://REPLACE_ME.data.go.kr/REPLACE_ME"

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


def main():
    raise NotImplementedError("2단계에서 구현 예정")


if __name__ == "__main__":
    main()
