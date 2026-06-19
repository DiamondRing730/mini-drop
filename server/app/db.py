"""Database engine / session factory."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

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
