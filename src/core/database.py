from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from src.core.config import settings

# Create the async engine
engine = create_async_engine(settings.DATABASE_URL, echo=True)

# Session factory for our endpoints to use
AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

# All models in users/models.py and documents/models.py will inherit from this
Base = declarative_base()


# Dependency to inject DB sessions into FastAPI routes
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
