"""DB engine 與 session 管理。

預設使用本機 SQLite（``stock_heat.db``）；以環境變數 ``STOCKHEAT_DATABASE_URL``
覆寫即可切換到 PostgreSQL（docs/05）。MVP 以 ``init_db`` 的 create_all 建立綱要；
正式環境改用 Alembic migration（docs/05 §6）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

_DEFAULT_URL = "sqlite:///stock_heat.db"

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def database_url() -> str:
    return os.environ.get("STOCKHEAT_DATABASE_URL", _DEFAULT_URL)


def get_engine(url: str | None = None) -> Engine:
    global _engine, _Session
    target = url or database_url()
    if _engine is None or str(_engine.url) != target:
        connect_args = {"check_same_thread": False} if target.startswith("sqlite") else {}
        _engine = create_engine(target, future=True, connect_args=connect_args)
        _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def init_db(url: str | None = None) -> Engine:
    """建立所有資料表（若不存在）。"""
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    """交易範圍：成功 commit、例外 rollback、結束 close。"""
    get_engine(url)
    assert _Session is not None
    session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
