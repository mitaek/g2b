#!/usr/bin/env bash
# 로컬 개발용 FastAPI 서버 실행 스크립트
set -euo pipefail
uvicorn src.api_server:app --host 0.0.0.0 --port 8000 --reload
