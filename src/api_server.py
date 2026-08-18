"""
FastAPI 백엔드.

엔드포인트 (3단계 이후 구현 예정):
  GET    /api/competitors
  POST   /api/competitors
  DELETE /api/competitors/{name}
  POST   /api/refresh
  GET    /api/refresh/status
  GET    /api/backfill-status
  GET    /api/dashboard-data
  GET    /api/unit-price

인증/로그인 미들웨어는 추가하지 않음 (오픈 접근).
필요시 nginx에서 IP 제한 또는 basic auth 추가 가능.
"""

from fastapi import FastAPI

app = FastAPI(title="Competitor Sales Dashboard API")


@app.get("/api/health")
def health():
    return {"status": "ok"}
