"""DB engine 與 session 管理。

預設使用本機 SQLite（``stock_heat.db``）；以環境變數 ``STOCKHEAT_DATABASE_URL``
覆寫即可切換到 PostgreSQL（docs/05）。MVP 以 ``init_db`` 的 create_all 建立綱要；
正式環境改用 Alembic migration（docs/05 §6）。
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

# create_all 在多執行緒下並非原子（先檢查再建立會 race）；以鎖序列化
_init_lock = threading.Lock()

_DEFAULT_URL = "sqlite:///stock_heat.db"

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def database_url() -> str:
    return os.environ.get("STOCKHEAT_DATABASE_URL", _DEFAULT_URL)


def _enable_sqlite_concurrency(engine: Engine) -> None:
    """SQLite：WAL + busy_timeout，讓背景寫入（如 seed）期間讀取不會被鎖死。

    WAL 允許讀者讀到上次提交的狀態而不阻塞；busy_timeout 讓偶發鎖等待而非報錯。
    """
    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn: object, _rec: object) -> None:  # noqa: ANN401
        cur = dbapi_conn.cursor()  # type: ignore[attr-defined]
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()


def get_engine(url: str | None = None) -> Engine:
    global _engine, _Session
    target = url or database_url()
    if _engine is None or str(_engine.url) != target:
        is_sqlite = target.startswith("sqlite")
        connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}
        _engine = create_engine(target, future=True, connect_args=connect_args)
        if is_sqlite:
            _enable_sqlite_concurrency(_engine)
        _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def init_db(url: str | None = None) -> Engine:
    """建立所有資料表（若不存在）。多執行緒下以鎖序列化，避免 create_all race。"""
    engine = get_engine(url)
    with _init_lock:
        Base.metadata.create_all(engine, checkfirst=True)
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
