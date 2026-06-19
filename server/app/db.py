"""Database engine / session factory."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

# SQLite (used by the unit tests) needs cross-thread access since FastAPI runs sync
# handlers in a threadpool; Postgres (prod) takes the pooling knobs instead.
if settings.database_url.startswith("sqlite"):
    engine = create_engine(
        settings.database_url, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,   # transparently recover from stale connections
        pool_size=10,
        max_overflow=20,
    )

# expire_on_commit=False so ORM objects stay usable after commit when building responses.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session():
    """FastAPI dependency: one Session per request, always closed."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
