import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Import component routers
from src.components.auth.router import router as auth_router
from src.components.documents.router import router as documents_router
from src.components.tenants.router import router as tenants_router
from src.components.tenants.permissions_router import router as permissions_router
from src.components.users.router import router as users_router
from src.components.users.repository import seed_default_lookups
from src.components.tenants.repository import (
    seed_default_plan_configs,
    seed_default_api_permissions,
)

# Assuming your settings are exposed here
from src.core.config import settings
from src.core.database import Base, engine

# ---------------------------------------------------------
# 1. Router Aggregation (The API Tree)
# ---------------------------------------------------------
api_v1_router = APIRouter(prefix=settings.API_V1_STR)

api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(tenants_router)
api_v1_router.include_router(permissions_router)
api_v1_router.include_router(documents_router)


# ---------------------------------------------------------
# 2. Lifespan Management
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup phase
    async with engine.begin() as conn:
        # 1. Ensure vector extension exists BEFORE creating tables
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

        try:
            await conn.execute(text("ALTER TYPE subscription_tier_enum ADD VALUE IF NOT EXISTS 'plus';"))
            await conn.execute(text("ALTER TYPE subscription_tier_enum ADD VALUE IF NOT EXISTS 'max';"))
            await conn.execute(text("ALTER TYPE subscription_tier_enum ADD VALUE IF NOT EXISTS 'PLUS';"))
            await conn.execute(text("ALTER TYPE subscription_tier_enum ADD VALUE IF NOT EXISTS 'MAX';"))
        except Exception:
            pass

        # 2. DEV ONLY: Create tables automatically.
        # IN PRODUCTION: Remove this line and use `alembic upgrade head`
        await conn.run_sync(Base.metadata.create_all)

        try:
            await conn.execute(text("ALTER TABLE plan_configs ADD COLUMN IF NOT EXISTS team_creator_roles VARCHAR(255) DEFAULT 'admin';"))
            await conn.execute(text("ALTER TABLE plan_configs ADD COLUMN IF NOT EXISTS allowed_features VARCHAR(1000) DEFAULT 'documents:upload,documents:read,rag:query,users:read,workspace:read';"))
        except Exception:
            pass

    # 3. Seed default system lookups, plan configurations, and API permission rules
    async with AsyncSession(engine) as session:
        await seed_default_lookups(session)
        await seed_default_plan_configs(session)
        await seed_default_api_permissions(session)


    yield  # Application is running

    # Teardown phase
    await engine.dispose()


# ---------------------------------------------------------
# 3. Application Factory Pattern
# ---------------------------------------------------------
def create_app() -> FastAPI:
    """
    Factory function to initialize and configure the FastAPI application.
    This pattern allows for easy testing and configuration injection.
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="AI Document Analyzer with RBAC and Quotas",
        version="1.0.0",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",  # Moves swagger schema to v1
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Configure CORS (Cross-Origin Resource Sharing)
    # In production, replace ["*"] with specific frontend domains e.g. ["https://myapp.com"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Attach the master router tree to the app
    app.include_router(api_v1_router)

    # Create the uploads folder if it doesn't exist
    os.makedirs("uploads", exist_ok=True)

    # Tell FastAPI to serve files from the "uploads" folder whenever someone goes to /static/...
    app.mount("/static", StaticFiles(directory="uploads"), name="static")

    # Global/Root endpoints
    @app.get("/", tags=["System"])
    async def root():
        return {
            "message": f"Welcome to {settings.PROJECT_NAME}",
            "docs_url": "/docs",
            "redoc_url": "/redoc",
            "health_url": "/health",
            "api_v1_prefix": settings.API_V1_STR,
        }

    @app.get("/health", tags=["System"])
    async def health_check():
        return {
            "status": "healthy",
            "environment": "production" if not settings.DEBUG else "development",
        }

    return app


# Initialize the application
app = create_app()


# ---------------------------------------------------------
# 4. Server Entrypoint
# ---------------------------------------------------------
if __name__ == "__main__":
    # Note: Ensure the string points to the actual file location.
    # If this file is src/main.py, the string must be "src.main:app"
    uvicorn.run("src.main:app", host="127.0.0.1", port=8002, reload=True)
