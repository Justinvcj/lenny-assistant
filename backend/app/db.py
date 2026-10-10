"""Database session and engine initialization using SQLAlchemy 2."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

# Convert standard postgresql+psycopg connection string if needed
db_url = settings.database_url
if "postgresql://" in db_url and not "postgresql+psycopg://" in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://")

engine = create_async_engine(
    db_url,
    echo=False,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db_session():
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
