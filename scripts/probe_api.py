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

load_dotenv()

BASE_URL = "https://apis.data.go.kr/1230000/at/ShoppingMallPrdctInfoService/getSpcifyPrdlstPrcureInfoList"
SERVICE_KEY = os.getenv("SERVICE_KEY", "REPLACE_ME")
DTL_PRDCT_NO = os.getenv("DTL_PRDCT_NOS", "4323300101").split(",")[0].strip()

CASES = [
    ("baseline: 7일, numOfRows=10", "20220101", "20220107", 10),
    ("numOfRows=500 (7일)", "20220101", "20220107", 500),
    ("numOfRows=100 (7일)", "20220101", "20220107", 100),
    ("날짜범위 30일, numOfRows=10", "20220101", "20220130", 10),
    ("날짜범위 90일, numOfRows=10", "20220101", "20220331", 10),
    ("날짜범위 180일, numOfRows=10", "20220101", "20220630", 10),
    ("날짜범위 270일, numOfRows=10", "20220101", "20220928", 10),
    ("날짜범위 364일, numOfRows=10", "20220101", "20221230", 10),
    ("날짜범위 365일, numOfRows=10", "20220101", "20221231", 10),
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
        text = resp.text
        if text.strip().startswith("{"):
            import json

            data = json.loads(text)
            header = data["response"]["header"]
            print(f"[{label}] resultCode={header.get('resultCode')} resultMsg={header.get('resultMsg')}")
        else:
            # XML 에러 응답에서 resultCode/resultMsg만 추출
            import re

            code = re.search(r"<resultCode>(.*?)</resultCode>", text)
            msg = re.search(r"<resultMsg>(.*?)</resultMsg>", text)
            print(
                f"[{label}] (XML) resultCode={code.group(1) if code else '?'} "
                f"resultMsg={msg.group(1) if msg else text[:200]}"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] EXCEPTION: {exc}")
