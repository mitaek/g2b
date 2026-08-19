"""
getSpcifyPrdlstPrcureInfoList API의 "입력범위값 초과 에러"(resultCode 07) 원인을
찾기 위한 1회성 진단 스크립트. 날짜 범위/numOfRows 조합을 바꿔가며 호출해보고
각각 resultCode를 출력합니다.

사용법: python scripts/probe_api.py
(.env의 SERVICE_KEY, DTL_PRDCT_NOS를 그대로 사용합니다)
"""

import os

import requests
from dotenv import load_dotenv

from src.collect_data import _parse_api_response

load_dotenv()

BASE_URL = "https://apis.data.go.kr/1230000/at/ShoppingMallPrdctInfoService/getSpcifyPrdlstPrcureInfoList"
SERVICE_KEY = os.getenv("SERVICE_KEY", "REPLACE_ME")
DTL_PRDCT_NO = os.getenv("DTL_PRDCT_NOS", "4323300101").split(",")[0].strip()

CASES = [
    ("364일 + numOfRows=500 (실패했던 바로 그 조합)", "20220101", "20221230", 500),
    ("364일 + numOfRows=250", "20220101", "20221230", 250),
    ("364일 + numOfRows=100", "20220101", "20221230", 100),
    ("364일 + numOfRows=50", "20220101", "20221230", 50),
    ("7일 + numOfRows=1000", "20220101", "20220107", 1000),
]

for label, bgn, end, num_of_rows in CASES:
    params = {
        "ServiceKey": SERVICE_KEY,
        "Type": "json",
        "inqryDiv": 1,
        "inqryBgnDate": bgn,
        "inqryEndDate": end,
        "inqryPrdctDiv": 2,
        "dtilPrdctClsfcNo": DTL_PRDCT_NO,
        "pageNo": 1,
        "numOfRows": num_of_rows,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=30)
        data = _parse_api_response(resp.text)
        header = data["header"]
        total_count = data["body"].get("totalCount", 0)
        print(
            f"[{label}] resultCode={header.get('resultCode')} "
            f"resultMsg={header.get('resultMsg')} totalCount={total_count}"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] EXCEPTION: {exc} / 응답 원문(앞 300자): {resp.text[:300]!r}")
