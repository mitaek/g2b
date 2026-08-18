"""
SQLAlchemy 모델 및 세션 관리.

DATABASE_URL 하나로 SQLite(로컬)/PostgreSQL(서버) 전환 가능하도록 작성.
TODO(2단계): competitors, delivery_requests, collection_runs, backfill_progress
모델 정의 및 Alembic 마이그레이션 연동.
"""

import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/app.db")
