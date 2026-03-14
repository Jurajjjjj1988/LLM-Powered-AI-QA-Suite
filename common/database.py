import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from common.exceptions import DatabaseError
from common.models import Base

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _get_engine(db_path: Path) -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        url = f"sqlite:///{db_path}"
        _engine = create_engine(url, connect_args={"check_same_thread": False})
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
        logger.info("Database engine created", extra={"db_path": str(db_path)})
    return _engine


def init_db(db_path: Path) -> None:
    engine = _get_engine(db_path)
    Base.metadata.create_all(engine)
    logger.info("Database tables ensured")


@contextmanager
def get_session(db_path: Path) -> Generator[Session, None, None]:
    _get_engine(db_path)
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        raise DatabaseError(f"Session error: {exc}") from exc
    finally:
        session.close()


@contextmanager
def get_readonly_session(db_path: Path) -> Generator[Session, None, None]:
    """
    Yield a read-only SQLAlchemy session.

    Enforces query_only per-connection via PRAGMA immediately after checkout
    rather than wiring a persistent engine-level event listener (which would
    accumulate duplicate listeners on every call and affect write sessions too).
    """
    _get_engine(db_path)
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        session.execute(text("PRAGMA query_only = ON"))
        yield session
    finally:
        session.close()
