# Developer Guide

This guide is designed to onboard developers to the **RAG Engine** codebase. It covers local setup, environment configuration, database management with `pgvector`, development workflows, and a step-by-step tutorial for adding new features.

---

## 1. Prerequisites & Tooling

Before getting started, ensure you have the following installed on your development machine:

- **Python**: Version `3.11` or `3.13` (64-bit).
- **Docker Desktop**: For running PostgreSQL (`pgvector`) and Redis containers.
- **Git**: For version control.
- **cURL / Postman / HTTP Client**: For testing endpoints (FastAPI also provides an interactive Swagger UI at `/docs`).

---

## 2. Environment Configuration (`.env`)

Create a `.env` file in the root directory by copying the provided [`.env.example`](file:///c:/Users/admin/Documents/Backup/rag_engine/.env.example):

```bash
cp .env.example .env
```

> [!TIP]
> For a full walkthrough on deploying this project online for free (with Neon.tech `pgvector`, Upstash Redis, and Render.com) along with ready-to-copy `.env` templates, refer to the [**Environment Configuration & Free Demo Deployment Guide**](file:///c:/Users/admin/Documents/Backup/rag_engine/docs/free_deployment_and_environment_guide.md).

### Configuration Reference Table

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `PROJECT_NAME` | `"RAG Engine API"` | Display name for the API documentation |
| `API_V1_STR` | `"/api/v1"` | URL prefix for all v1 API routes |
| `DEBUG` | `true` | Enables reload mode and debug logs |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:mysecretpassword@localhost:5434/rag_db` | PostgreSQL async connection string |
| `REDIS_URL` | `redis://localhost:6380/0` | Redis connection URL |
| `SECRET_KEY` | `change-this-to-a-very-long-and-secure-random-secret-key-32chars` | Secret key for JWT signing (HS256) |
| `ALGORITHM` | `"HS256"` | JWT signature algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` | Token lifetime (default: 7 days) |
| `DEFAULT_AI_PROVIDER` | `"openai"` | Default AI provider (`openai`) |
| `OPENAI_API_KEY` | `sk-...` | Your OpenAI API key for embeddings & chat |
| `STORAGE_BACKEND` | `"local"` | Storage engine: `"local"` or `"s3"` |
| `LOCAL_UPLOAD_DIR` | `"uploads"` | Local folder where files are stored |
| `AWS_ACCESS_KEY_ID` | `None` | AWS credentials (if `STORAGE_BACKEND=s3`) |
| `AWS_SECRET_ACCESS_KEY` | `None` | AWS secret key (if `STORAGE_BACKEND=s3`) |
| `AWS_REGION_NAME` | `"us-east-1"` | AWS S3 region |
| `S3_BUCKET_NAME` | `None` | Target S3 bucket name |
| `AWS_ENDPOINT_URL` | `None` | Custom S3 endpoint (for MinIO / LocalStack) |

> [!IMPORTANT]
> If running the app **inside Docker**, set `DATABASE_URL` to point to `@db:5432/rag_db` and `REDIS_URL` to `redis://redis:6379/0`.
> If running the app **locally on your host** (outside Docker), use port `5434` for DB and `6380` for Redis.

---

## 3. Running the Project

### Option A: Hybrid Workflow (Recommended for Fast Local Iteration)

Run PostgreSQL with `pgvector` and Redis inside Docker, while running the FastAPI application natively with live reload:

1. **Start Database and Redis containers**:
   ```bash
   docker compose up -d db redis
   ```
2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   # On Windows PowerShell:
   .\venv\Scripts\Activate.ps1
   # On macOS/Linux:
   source venv/bin/activate
   ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Start the FastAPI application**:
   ```bash
   uvicorn src.main:app --host 127.0.0.1 --port 8002 --reload
   ```
5. **Open Swagger UI**:
   Visit [http://127.0.0.1:8002/docs](http://127.0.0.1:8002/docs) in your browser.

---

### Option B: Full Containerized Setup

To launch the entire stack (App, pgvector DB, Redis) with a single command:

```bash
docker compose up -d --build
```

- Application runs at: [http://localhost:8002](http://localhost:8002)
- Logs can be viewed with: `docker compose logs -f app`

---

## 4. Database Lifecycle & pgvector Initialization

When the application boots up, [`lifespan`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/main.py#L36-L51) in [`src/main.py`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/main.py) executes two critical tasks:

```python
async with engine.begin() as conn:
    # 1. Ensure the pgvector extension exists BEFORE creating tables
    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

    # 2. DEV ONLY: Create tables automatically
    await conn.run_sync(Base.metadata.create_all)
```

> [!WARNING]
> In production environments, remove `conn.run_sync(Base.metadata.create_all)` and manage schema changes using **Alembic** migrations (`alembic upgrade head`).

---

## 5. Step-by-Step: Adding a New Feature Component

Follow the repository's 5-layer domain pattern when building a new component (e.g. `src/components/analytics/`):

```mermaid
graph LR
    Model["1. models.py"] --> Schema["2. schemas.py"]
    Schema --> Repo["3. repository.py"]
    Repo --> Service["4. service.py"]
    Service --> Router["5. router.py"]
    Router --> Main["6. src/main.py"]
```

### Step 1: Define the Model (`models.py`)
Inherit from `Base` in [`src/core/database.py`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/core/database.py):
```python
from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base

class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
```

### Step 2: Define Schemas (`schemas.py`)
Create input and output Pydantic DTOs:
```python
from pydantic import BaseModel, ConfigDict

class AnalyticsEventCreate(BaseModel):
    event_type: str

class AnalyticsEventResponse(AnalyticsEventCreate):
    id: int
    tenant_id: int

    model_config = ConfigDict(from_attributes=True)
```

### Step 3: Implement the Repository (`repository.py`)
Isolate database operations:
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .models import AnalyticsEvent

class AnalyticsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, tenant_id: int, event_type: str) -> AnalyticsEvent:
        event = AnalyticsEvent(tenant_id=tenant_id, event_type=event_type)
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event
```

### Step 4: Implement Business Logic (`service.py`)
Encapsulate rules and external service integrations:
```python
from .repository import AnalyticsRepository
from .schemas import AnalyticsEventCreate

class AnalyticsService:
    def __init__(self, repository: AnalyticsRepository):
        self.repository = repository

    async def log_event(self, tenant_id: int, data: AnalyticsEventCreate):
        return await self.repository.create(tenant_id=tenant_id, event_type=data.event_type)
```

### Step 5: Implement the Router (`router.py`)
Wire dependencies, roles, and endpoints:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.deps import get_current_user
from src.components.users.models import User
from .repository import AnalyticsRepository
from .service import AnalyticsService
from .schemas import AnalyticsEventCreate, AnalyticsEventResponse

router = APIRouter(prefix="/analytics", tags=["Analytics"])

def get_analytics_service(session: AsyncSession = Depends(get_db)) -> AnalyticsService:
    return AnalyticsService(AnalyticsRepository(session))

@router.post("/", response_model=AnalyticsEventResponse)
async def create_event(
    payload: AnalyticsEventCreate,
    service: AnalyticsService = Depends(get_analytics_service),
    current_user: User = Depends(get_current_user),
):
    return await service.log_event(tenant_id=current_user.tenant_id, data=payload)
```

### Step 6: Register in `src/main.py`
Add the router to `api_v1_router`:
```python
from src.components.analytics.router import router as analytics_router

api_v1_router.include_router(analytics_router)
```

---

## 6. Authentication & RBAC in Endpoint Development

### Requiring Authentication
Inject [`get_current_user`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/core/deps.py#L18-L77):
```python
@router.get("/profile")
async def profile(current_user: User = Depends(get_current_user)):
    return current_user
```

### Restricting Access by Role
Use the [`RequireRole`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/core/deps.py#L83-L101) dependency factory:
```python
@router.delete("/purge")
async def purge_data(
    current_user: User = Depends(RequireRole([UserRole.ADMIN, UserRole.MAINTAINER]))
):
    # Only Admin or Maintainer can execute this
    ...
```

### Checking Role Hierarchy Programmatically
Use [`has_minimum_role`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/core/permissions.py#L19-L20):
```python
from src.core.permissions import has_minimum_role

if not has_minimum_role(current_user.user_role, UserRole.MANAGER):
    raise HTTPException(status_code=403, detail="Manager level required.")
```

---

## 7. Useful Redis & Database Commands for Debugging

### Inspecting Redis
Connect to the Redis container:
```bash
docker exec -it rag_engine_redis redis-cli
```
- **Check cached users**: `KEYS user_cache:*`
- **Inspect cached user JSON**: `GET user_cache:1`
- **Inspect daily tenant quota**: `GET quota:tenant:1:date:2026-10-01`
- **Check TTL of key**: `TTL quota:tenant:1:date:2026-10-01`

### Inspecting PostgreSQL & pgvector
Connect to the PostgreSQL container:
```bash
docker exec -it rag_engine_db psql -U postgres -d rag_db
```
- **List installed extensions**: `\dx`
- **View table definitions**: `\d documents` and `\d document_chunks`
- **Check chunk embedding dimensions**:
  ```sql
  SELECT id, document_id, chunk_index, length(embedding) FROM document_chunks LIMIT 5;
  ```
