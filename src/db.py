"""
SQLAlchemy 모델 및 세션 관리.

DATABASE_URL 하나로 SQLite(로컬)/PostgreSQL(서버) 전환 가능하도록 작성.
"""

import os
from contextlib import contextmanager
from datetime import datetime, date, timezone

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()


def utcnow():
    """datetime.utcnow()의 deprecation-safe 대체 (naive UTC datetime 유지)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/app.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_self = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    deleted_at = Column(DateTime, nullable=True)


class DeliveryRequest(Base):
    __tablename__ = "delivery_requests"

    id = Column(Integer, primary_key=True)
    dcisn_dt = Column(Date, nullable=True)
    corp_nm = Column(String, nullable=False)
    corp_biz_no = Column(String, nullable=True)
    contract_no = Column(String, nullable=True)
    dlvr_req_no = Column(String, nullable=False)
    dlvr_req_chg_cha = Column(Integer, nullable=False, default=0)
    prdct_sno = Column(Integer, nullable=False, default=0)
    prdct_clsfc_nm = Column(String, nullable=True)
    dtl_prdct_nm = Column(String, nullable=True)
    dmnd_instt_nm = Column(String, nullable=True)
    dlvr_amt = Column(Numeric, nullable=True)
    dlvr_qty = Column(Numeric, nullable=True)
    raw_json = Column(Text, nullable=True)
    collected_at = Column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "dlvr_req_no",
            "dlvr_req_chg_cha",
            "prdct_sno",
            name="uq_delivery_request_identity",
        ),
        Index("ix_delivery_requests_corp_nm", "corp_nm"),
        Index("ix_delivery_requests_dmnd_instt_nm", "dmnd_instt_nm"),
        Index("ix_delivery_requests_dtl_prdct_nm", "dtl_prdct_nm"),
        Index("ix_delivery_requests_dcisn_dt", "dcisn_dt"),
    )


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, nullable=False, default=utcnow)
    finished_at = Column(DateTime, nullable=True)
    date_from = Column(Date, nullable=True)
    date_to = Column(Date, nullable=True)
    rows_fetched = Column(Integer, nullable=False, default=0)
    rows_upserted = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="success")  # success|failed
    error_message = Column(Text, nullable=True)


class BackfillProgress(Base):
    __tablename__ = "backfill_progress"

    id = Column(Integer, primary_key=True)
    target_year = Column(Integer, nullable=False, unique=True)
    status = Column(String, nullable=False, default="pending")  # pending|in_progress|done|failed
    rows_fetched = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
