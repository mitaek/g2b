# 경쟁사 매출 대시보드 (나라장터 종합쇼핑몰)

공공데이터포털 "조달청_종합쇼핑몰 납품요구 물품 내역" API로 경쟁사들의
매출 데이터를 수집·축적하고, 웹 대시보드로 시각화하는 프로젝트입니다.

- Backend: FastAPI + SQLAlchemy (로컬 SQLite / 서버 PostgreSQL)
- Frontend: 정적 HTML + fetch 기반 렌더링 (다크 테마, 외부 CDN 의존성 없는 자체 SVG 차트)
- 데이터 수집: 공공데이터포털 API, 최초 5개년 백필 후 매주 일요일 자동 갱신
- 로그인/인증 없음 (오픈 접근). 필요시 nginx에서 IP 제한 또는 basic auth 추가 가능.

## 프로젝트 구조

```
/src
  collect_data.py    # API 수집 + DB 적재 (--full-backfill, --daily-chunk, --weekly, --mock)
  build_dashboard.py # (레거시 자리) 집계 로직은 aggregations.py로 분리되어 재사용됨
  api_server.py      # FastAPI 백엔드
  db.py              # SQLAlchemy 모델/세션
  aggregations.py    # 대시보드용 집계 쿼리 모음
/static
  competitor_dashboard.html  # 프론트엔드 (fetch 기반)
/migrations           # Alembic 마이그레이션
/data                  # app.db(SQLite) 등 - git 제외
/config
  systemd/            # competitor-dashboard.service, backfill/weekly timer
  nginx/               # reverse proxy 설정 예시
  cron/                 # systemd timer 대신 cron 사용 시 예시
/scripts
  backup.sh            # PostgreSQL pg_dump 기반 백업
.github/workflows/deploy.yml  # SSH 배포 워크플로우 초안
.env.example
requirements.txt
run.sh                 # uvicorn 실행 스크립트
```

## 진행 상태

1~7단계(프로젝트 구조, DB 스키마, FastAPI 백엔드, 프론트엔드, 수집 모드,
GitHub 연동, 서버 배포 준비 파일) 모두 완료되었습니다.
서버가 아직 없어 배포 자체는 진행되지 않았고, 서버 준비 시 아래 안내를 따르면 됩니다.

## 로컬 실행

1. `.env` 설정 (`.env.example` 참고 — `SERVICE_KEY`, `BASE_URL`은 공공데이터포털
   Swagger에서 확인해서 채워야 하고, `src/collect_data.py`의 `FIELD_MAP`도 실제
   응답 필드명에 맞게 수정해야 합니다)
2. `pip install -r requirements.txt`
3. `alembic upgrade head`
4. `python -m src.collect_data --full-backfill --daily-chunk`
   (실제 API 연동 전에는 `--mock` 플래그로 동작만 검증할 수 있습니다)
5. `bash run.sh` → http://localhost:8000
6. 이후 매주 일요일 `--weekly` 자동 갱신 (cron 또는 systemd timer 설정 시)

## 데이터 갱신 주기

원본 API는 D-1 기준 데이터를 제공합니다. 최초 5개년 백필 후, 매주 일요일
새벽에 지난 주(월~일) 데이터를 갱신합니다. API 호출에는 트래픽 제한이
있을 수 있으니 `--full-backfill --daily-chunk`로 하루 한 연도씩 나눠
수집하는 것을 권장합니다. 단가/매출 수치는 계약 조건에 따라 달라질 수
있으므로 참고용으로만 활용하세요.

## 서버 배포

1. 서버에 저장소를 clone하고 `/opt/competitor-dashboard`(또는 원하는 경로)에 배치,
   `.venv` 생성 후 `pip install -r requirements.txt`, `.env` 설정, `alembic upgrade head`
2. `config/systemd/competitor-dashboard.service`를 `/etc/systemd/system/`에 복사 후
   `systemctl enable --now competitor-dashboard` (경로/계정은 파일 내 TODO 참고해서 교체)
3. 데이터 갱신은 systemd timer(`config/systemd/competitor-backfill.{service,timer}`,
   `competitor-weekly.{service,timer}`) 또는 `config/cron/crontab.example` 중 하나를
   선택해서 등록
4. `config/nginx/competitor-dashboard.conf`를 참고해 reverse proxy 설정
   (server_name 교체 필수. 필요시 IP 제한/basic auth 주석 해제)
5. GitHub Actions 자동 배포(`.github/workflows/deploy.yml`)를 쓰려면 저장소
   Settings → Secrets and variables → Actions에 다음 값을 등록:
   - `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`
   - (주의: `SERVICE_KEY`, `DATABASE_URL` 등 앱의 `.env` 값은 이 워크플로우가
     건드리지 않습니다. 서버의 `.env` 파일에 직접 설정해두세요)
6. DB 백업: PostgreSQL은 `scripts/backup.sh` (pg_dump 기반, cron으로 주기 실행 권장),
   SQLite는 `cp data/app.db backups/app-$(date +%F).db`로 파일 복사

## 참고

이 저장소는 원래 "Todo 앱" 프로젝트로 시작되었으나, 요청에 따라
경쟁사 매출 대시보드 프로젝트로 새로 구성되었습니다.
