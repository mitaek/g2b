# 경쟁사 매출 대시보드 (나라장터 종합쇼핑몰)

공공데이터포털 "조달청_종합쇼핑몰 납품요구 물품 내역" API로 경쟁사들의
매출 데이터를 수집·축적하고, 웹 대시보드로 시각화하는 프로젝트입니다.

- Backend: FastAPI + SQLAlchemy (로컬 SQLite / 서버 PostgreSQL)
- Frontend: 정적 HTML + fetch 기반 렌더링 (다크 테마)
- 데이터 수집: 공공데이터포털 API, 최초 5개년 백필 후 매주 일요일 자동 갱신
- 로그인/인증 없음 (오픈 접근). 필요시 nginx에서 IP 제한 또는 basic auth 추가 가능.

## 프로젝트 구조

```
/src
  collect_data.py    # API 수집 + DB 적재
  build_dashboard.py # (레거시 자리) 집계 로직은 aggregations.py로 분리되어 재사용됨
  api_server.py      # FastAPI 백엔드
  db.py              # SQLAlchemy 모델/세션
  aggregations.py    # 대시보드용 집계 쿼리 모음
/static
  competitor_dashboard.html  # 프론트엔드 (fetch 기반)
/migrations           # Alembic 마이그레이션
/data                  # app.db(SQLite), competitors 관련 파일 등 - git 제외
/config
/scripts
  backup.sh
.env.example
requirements.txt
run.sh                 # uvicorn 실행 스크립트
```

## 진행 상태

현재 **1단계(프로젝트 구조 + .env 분리 + requirements.txt)**까지 완료되었습니다.
이후 단계(DB 스키마/Alembic, FastAPI 엔드포인트, 프론트엔드, 수집 모드,
GitHub 연동, 서버 배포 준비)는 순차적으로 진행됩니다.

## 로컬 실행 (다음 단계 완료 후)

1. `.env` 설정 (`.env.example` 참고 — `SERVICE_KEY`, `BASE_URL`은 공공데이터포털
   Swagger에서 확인해서 채워야 합니다)
2. `pip install -r requirements.txt`
3. `alembic upgrade head` (2단계에서 마이그레이션 추가 예정)
4. `python src/collect_data.py --full-backfill --daily-chunk`
5. `bash run.sh` → http://localhost:8000

## 참고

이 저장소는 원래 "Todo 앱" 프로젝트로 시작되었으나, 요청에 따라
경쟁사 매출 대시보드 프로젝트로 새로 구성되었습니다.
