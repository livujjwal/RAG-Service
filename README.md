# RAG-Service: Enterprise Multi-Tenant RAG & Vector Intelligence Engine

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Python-3.11%20%7C%203.13-3776AB.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-336791.svg?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Redis-7.0-DC382D.svg?style=for-the-badge&logo=redis&logoColor=white" alt="Redis" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED.svg?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/OpenAI-text--embedding--3--small-412991.svg?style=for-the-badge&logo=openai&logoColor=white" alt="OpenAI" />
  <img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="License" />
</p>

---

## Executive Summary

**RAG-Service** is a production-ready, high-throughput, multi-tenant **Retrieval-Augmented Generation (RAG)** backend built with **FastAPI**, **PostgreSQL 16 with `pgvector`**, **Async SQLAlchemy 2.0**, and **Redis**.

Engineered for strict organizational multi-tenancy and enterprise scale, the platform co-locates relational workspace metadata with high-dimensional vector embeddings in PostgreSQL. It features an automated public signup pipeline with tenant workspace auto-provisioning, hierarchical Role-Based Access Control (RBAC), subscription plan quota enforcement (seat limits and daily token budgets), pluggable AI providers (OpenAI, extensible to Anthropic/MCP), and pluggable storage backends (Async Local Filesystem or AWS S3 / MinIO / Cloudflare R2).

---

## Key Capabilities & Highlights

- **ACID Vector Co-Location (`pgvector`)**: Stores 1536-dimensional embeddings directly in PostgreSQL 16 using `pgvector`. Eliminates vector-relational synchronization drift, simplifies backups, and enables transactional document chunk deletions with foreign key cascades.
- **Strict Multi-Tenant Isolation**: Hard separation between tenant workspaces at the SQL query and vector index level. Workspace data, embeddings, and documents remain strictly isolated.
- **Hierarchical RBAC & Dynamic Access Matrix**: Two user scopes (`INTERNAL` platform superusers and `EXTERNAL` workspace users) with an 8-level role hierarchy (`super_admin`, `admin`, `maintainer`, `manager`, `team_lead`, `account_manager`, `consultant`, `associate`).
- **Subscription Tier & Quota Engine**: Configurable tiers (`Free`, `Plus`, `Pro`, `Max`, `Enterprise`) that dynamically govern maximum workspace user seats, daily token allowances, assignable team roles, and permitted API features.
- **Redis-Backed Real-Time Rate & Token Limiting**: Atomically tracks and meters daily token ingestion quotas per tenant with sub-millisecond overhead using Redis.
- **Pluggable AI Provider Architecture (Factory Pattern)**: Decoupled AI provider layer (`AIFactory` & `BaseAIProvider`) supporting OpenAI (`text-embedding-3-small`, `gpt-4o`) with planned support for Anthropic and Model Context Protocol (MCP) tool execution.
- **Pluggable Async Object Storage (Factory Pattern)**: `StorageFactory` allows switching between local asynchronous filesystem storage and AWS S3 / Cloudflare R2 / MinIO via `aioboto3` without changing business logic.
- **End-to-End Async Pipeline**: Built entirely on non-blocking async primitives (`asyncio`, `asyncpg`, `redis.asyncio`, `aiofiles`).

---

## System Architecture

### High-Level Topology

```mermaid
graph TB
    subgraph ClientLayer ["Client & Ingestion Layer"]
        Client["Web Apps / Mobile Clients / API Consumers"]
    end

    subgraph FastAPIServer ["FastAPI Engine (Port 8002)"]
        RouterTree["Router Tree (/api/v1)"]
        SecurityMiddleware["FastAPI Depends (OAuth2 / JWT / RBAC)"]

        subgraph DomainComponents ["Modular Domain Components"]
            AuthComp["AuthService (src/components/auth)"]
            UserComp["UserService (src/components/users)"]
            TenantComp["TenantService (src/components/tenants)"]
            DocComp["DocumentService (src/components/documents)"]
        end

        subgraph CoreSubsystems ["Core & Factory Layer"]
            Security["Security (Bcrypt & PyJWT)"]
            StorageFact["StorageFactory (Local / S3)"]
            AIFact["AIFactory (OpenAI / MCP)"]
        end
    end

    subgraph PersistenceInfra ["Data & Vector Infrastructure"]
        PostgresDB[("PostgreSQL 16 + pgvector<br/>(Port 5434 / 5432)<br/>Relational Data + 1536-dim Chunks")]
        RedisCache[("Redis 7.0<br/>(Port 6380 / 6379)<br/>Token Quotas & Caching")]
        FileStore[("Object Storage<br/>(Local Uploads / AWS S3 / R2)")]
    end

    subgraph ExternalAI ["External AI Services"]
        OpenAIAPI["OpenAI API<br/>(Embeddings & Chat Completions)"]
    end

    Client --> RouterTree
    RouterTree --> SecurityMiddleware
    SecurityMiddleware --> DomainComponents
    DomainComponents --> CoreSubsystems
    DocComp --> StorageFact
    DocComp --> AIFact
    StorageFact --> FileStore
    AIFact --> OpenAIAPI
    DomainComponents --> PostgresDB
    DomainComponents --> RedisCache
    SecurityMiddleware --> RedisCache
```

### Document Ingestion & RAG Vector Pipeline

```mermaid
sequenceDiagram
    autonumber
    actor User as Client (Workspace User)
    participant API as /api/v1/documents/upload
    participant Quota as TenantService (Redis)
    participant Storage as StorageProvider (Local/S3)
    participant AI as AIProvider (OpenAI)
    participant DB as PostgreSQL (pgvector)

    User->>API: POST /upload (PDF binary multipart)
    API->>Quota: Verify & Deduct Token Quota (Tenant ID)
    alt Quota Exceeded
        Quota-->>API: 429 / 403 Daily Token Limit Reached
        API-->>User: Quota Exceeded Error
    else Quota Approved
        Quota-->>API: Quota Reserved
        API->>Storage: Store Raw Asset (UUID filename)
        Storage-->>API: File URL / Object Reference
        API->>DB: INSERT into documents table
        API->>API: PyPDF Text Extraction & Recursive Chunking
        API->>AI: Generate Embeddings (text-embedding-3-small)
        AI-->>API: 1536-dim Vector Embeddings
        API->>DB: Batch INSERT document_chunks (text + vector)
        API-->>User: 200 OK (Document ID, Consumed Tokens, Remaining Quota)
    end
```

---

## Tech Stack & Specifications

| Layer | Technology | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **API Framework** | [FastAPI](https://fastapi.tiangolo.com/) | `>=0.115.0` | High-performance asynchronous REST API framework |
| **ASGI Web Server** | [Uvicorn](https://www.uvicorn.org/) | `>=0.30.0` | Lightning-fast ASGI server with reload support |
| **Database Engine** | [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) | `16` / `>=0.3.0` | Unified ACID relational metadata and vector storage |
| **ORM & Driver** | [SQLAlchemy](https://www.sqlalchemy.org/) + [asyncpg](https://github.com/MagicStack/asyncpg) | `2.0.30` / `>=0.29.0` | Async Python SQL toolkit and Postgres driver |
| **Cache & Quota Metering** | [Redis](https://redis.io/) (`redis.asyncio`) | `7-alpine` / `>=5.0.0` | Sub-millisecond token counters and session caching |
| **Validation & Settings** | [Pydantic](https://docs.pydantic.dev/) + [pydantic-settings](https://github.com/pydantic/pydantic-settings) | `>=2.8.0` / `>=2.4.0` | Strict data typing and environment configuration |
| **Authentication & Crypto** | [PyJWT](https://pyjwt.readthedocs.io/) + [Bcrypt](https://github.com/pyca/bcrypt) | `>=2.9.0` / `>=4.2.0` | JWT bearer token lifecycle and password salt hashing |
| **AI & Embeddings** | [OpenAI Python SDK](https://github.com/openai/openai-python) | `>=1.40.0` | 1536-dimensional embeddings and LLM generation |
| **Chunking & Parsers** | [LangChain Text Splitters](https://python.langchain.com/) + [pypdf](https://pypdf.readthedocs.io/) | `>=0.2.0` / `>=4.3.0` | Intelligent document boundary splitting and PDF parsing |
| **Storage Abstraction** | [aiofiles](https://github.com/Tinche/aiofiles) + [aioboto3](https://github.com/terrycain/aioboto3) | `>=24.1.0` / `>=13.1.0` | Async local filesystem and AWS S3/MinIO cloud storage |
| **Containerization** | [Docker](https://www.docker.com/) & [Docker Compose](https://docs.docker.com/compose/) | Compose v2 | Multi-service local orchestration and deployments |

---

## Repository Structure

```text
rag_engine/
├── docs/                                    # Comprehensive Technical Documentation
│   ├── README.md                            # Documentation Hub & Navigation Index
│   ├── developer_guide.md                   # Onboarding, testing, and debugging workflows
│   ├── project_architecture_guide.md        # Modular Monolith & System Architecture
│   ├── rag_architecture_guide.md            # Technical blueprint of the RAG & vector subsystem
│   ├── rag_workflow.md                      # Ingestion, chunking, and similarity math
│   ├── plans_and_permissions_guide.md       # Subscription tiers, seat caps, and RBAC matrix
│   ├── workflow_api_models_router_...md     # Data flow through Router-Service-Repo layers
│   ├── free_cloud_databases_guide.md        # Free-tier cloud setup (Neon, Supabase, Upstash)
│   └── free_deployment_and_environment_... # Zero-cost deployment to Render and cloud PaaS
├── scripts/                                 # Platform Administration & Verification CLI
│   ├── create_internal_admin.py             # Provision or promote an Internal Platform Superuser
│   └── test_plan_and_role_access.py         # End-to-end plan limits & RBAC verification suite
├── src/                                     # Application Source Code
│   ├── ai/                                  # AI Provider Engine (Factory Pattern)
│   │   ├── factory.py                       # Dynamic runtime AI provider resolution
│   │   ├── interfaces.py                    # BaseAIProvider contract
│   │   └── providers/                       # Concrete AI providers (OpenAI, etc.)
│   ├── components/                          # Domain-Driven Components
│   │   ├── auth/                            # User registration, OAuth2 login, JWT issuance
│   │   ├── documents/                       # PDF parsing, chunking, pgvector embeddings
│   │   ├── tenants/                         # Multi-tenancy, workspace quotas, plan configs
│   │   └── users/                           # User management, profile lookups, team seats
│   ├── core/                                # Cross-Cutting Infrastructure
│   │   ├── config.py                        # Pydantic Settings & environment variables
│   │   ├── database.py                      # SQLAlchemy Async Engine, Base, and SessionLocal
│   │   ├── deps.py                          # FastAPI Dependency Injection (Auth, Quotas, RBAC)
│   │   ├── permissions.py                   # Role definitions & hierarchy utilities
│   │   ├── redis.py                         # Shared async Redis client
│   │   └── security.py                      # Password hashing (Bcrypt) and JWT tokens
│   ├── storage/                             # Storage Engine (Factory Pattern)
│   │   ├── factory.py                       # Dynamic runtime storage provider selection
│   │   ├── interfaces.py                    # BaseStorageProvider contract
│   │   ├── local_storage.py                 # Async local filesystem implementation
│   │   └── s3_storage.py                    # AWS S3 / MinIO / Cloudflare R2 implementation
│   └── main.py                              # FastAPI Application Factory, router tree, lifespan
├── uploads/                                 # Local uploads directory for stored documents
├── .env.example                             # Environment variables template
├── docker-compose.yml                       # Multi-service stack (App, pgvector, Redis)
├── Dockerfile                               # Production Docker build definition
└── requirements.txt                         # Application Python dependencies
```

---

## Getting Started

### 1. Prerequisites

- **Python**: Version `3.11` or `3.13` (64-bit)
- **Docker Desktop**: Engine 24+ and Compose v2
- **OpenAI API Key**: Required for vector embeddings (`text-embedding-3-small`) and LLM chat completions
- **Git**

### 2. Environment Configuration

Clone the repository and instantiate your `.env` configuration file:

```bash
cp .env.example .env
```

Edit `.env` to configure your keys and ports:

```dotenv
# Application
PROJECT_NAME="RAG Engine API"
API_V1_STR="/api/v1"
DEBUG=true

# Database (PostgreSQL with pgvector)
# When running via Docker Compose:
DATABASE_URL=postgresql+asyncpg://postgres:mysecretpassword@db:5432/rag_db
# When running locally on host machine:
# DATABASE_URL=postgresql+asyncpg://postgres:mysecretpassword@localhost:5434/rag_db

POSTGRES_USER=postgres
POSTGRES_PASSWORD=mysecretpassword
POSTGRES_DB=rag_db

# Redis (Caching & Quota Rate Limiting)
# When running via Docker Compose:
REDIS_URL=redis://redis:6379/0
# When running locally on host machine:
# REDIS_URL=redis://localhost:6380/0

# Security
SECRET_KEY=generate-a-secure-random-32-byte-hex-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# AI Provider
DEFAULT_AI_PROVIDER=openai
OPENAI_API_KEY=sk-proj-yourOpenAIKeyHere

# Storage Provider (local or s3)
STORAGE_BACKEND=local
LOCAL_UPLOAD_DIR=uploads
```

---

## Deployment & Running Modes

### Option A: Complete Docker Compose Stack (Recommended)

Orchestrates the entire stack (`rag_engine_app`, `pgvector/pgvector:pg16`, and `redis:7-alpine`) with built-in healthchecks and shared networks:

```bash
# Build and start all services in detached mode
docker compose up -d --build

# Inspect running containers
docker compose ps

# Follow application logs
docker compose logs -f app
```

- **Interactive API Documentation (Swagger)**: [http://localhost:8002/docs](http://localhost:8002/docs)
- **Alternative API Documentation (ReDoc)**: [http://localhost:8002/redoc](http://localhost:8002/redoc)
- **Health Check Endpoint**: [http://localhost:8002/health](http://localhost:8002/health)

---

### Option B: Hybrid Development Mode (Rapid Local Iteration)

Run PostgreSQL (`pgvector`) and Redis in Docker while executing the FastAPI application directly on your host machine for instant hot-reloading and native IDE debugging.

1. **Spin up PostgreSQL and Redis containers only**:
   ```bash
   docker compose up -d db redis
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install project dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Adjust `.env` to target the host exposed ports**:
   ```dotenv
   DATABASE_URL=postgresql+asyncpg://postgres:mysecretpassword@localhost:5434/rag_db
   REDIS_URL=redis://localhost:6380/0
   ```

5. **Start the FastAPI development server**:
   ```bash
   uvicorn src.main:app --host 127.0.0.1 --port 8002 --reload
   ```

---

### Option C: 100% Free Cloud Infrastructure ($0/month)

Deploy the system without maintaining local infrastructure:
- **Database**: [Neon.tech](https://neon.tech/) (Free Serverless PostgreSQL 16 with native `pgvector`) or [Supabase](https://supabase.com/)
- **Redis**: [Upstash](https://upstash.com/) (Free Serverless Redis with TLS)
- **Object Storage**: [Cloudflare R2](https://www.cloudflare.com/products/r2/) (10GB free S3-compatible storage with zero egress fees)
- **App Hosting**: [Render.com](https://render.com/) or [Railway](https://railway.app/)

> [!TIP]
> Follow the complete step-by-step tutorial with ready-made `.env` connection templates in [`docs/free_cloud_databases_guide.md`](file:///docs/free_cloud_databases_guide.md) and [`docs/free_deployment_and_environment_guide.md`](file:///docs/free_deployment_and_environment_guide.md).

---

## Administrative CLI Tools

### 1. Provision Platform Internal Admin (Superuser)

Internal Admins possess global scope (`tenant_id = None`), bypass workspace token quotas, and can manage subscription plans, tier configurations, and API permission matrices.

```bash
# Execute on host
python scripts/create_internal_admin.py --email admin@example.com --password SuperSecurePassword123!

# Or inside Docker container
docker exec -it rag_engine_app python scripts/create_internal_admin.py --email admin@example.com --password SuperSecurePassword123!
```

### 2. Verify Plan Quotas & Access Control Matrix

Run the automated verification suite to validate user signup, workspace auto-provisioning, seat limits, role assignment guardrails, and dynamic API permission evaluation:

```bash
# Execute on host
python scripts/test_plan_and_role_access.py

# Or inside Docker container
docker exec -it rag_engine_app python scripts/test_plan_and_role_access.py
```

---

## Subscription Plans & Multi-Tenancy Quotas

Workspaces are bound to a subscription plan tier configured in PostgreSQL (`plan_configs`):

| Tier | Display Name | Max Users (`max_users`) | Daily Token Quota | Team Management | Allowed Creator Roles | Assignable Member Roles |
| :---: | :--- | :---: | :---: | :---: | :--- | :--- |
| **`free`** | Free Tier | **1** | 50,000 | 🔒 Disabled | `admin` | `associate` |
| **`plus`** | Plus Tier | **5** | 250,000 | ✅ Enabled | `admin` | `associate, consultant` |
| **`pro`** | Pro Tier | **25** | 1,000,000 | ✅ Enabled | `admin, manager` | `associate, consultant, team_lead, manager` |
| **`max`** | Max Tier | **100** | 5,000,000 | ✅ Enabled | `admin, manager` | `associate, consultant, team_lead, manager, account_manager` |
| **`enterprise`** | Enterprise Tier | **10,000** | 999,999,999 | ✅ Enabled | `admin, maintainer, manager` | *All Roles* |

### Team Creation & Seat Guardrails
When an External Admin adds team members via `POST /api/v1/users/`:
1. **Seat Limit Validation**: If active workspace members reach `plan_config.max_users`, the system returns `HTTP 403 Forbidden` (`User limit reached for Plan`).
2. **Role Whitelist**: Only roles listed in `plan_config.allowed_roles` can be assigned. Any unauthorized role assignment is rejected with `HTTP 403 Forbidden`.
3. **Workspace Isolation**: Created users are strictly pinned to `creator.tenant_id` with `user_type = EXTERNAL`.

---

## API Reference & Core Workflows

The REST API is versioned under `/api/v1`. Comprehensive OpenAPI specifications are interactively accessible at `/docs`.

### Primary Endpoint Overview

| Module | Route | Method | Access Level | Description |
| :--- | :--- | :---: | :---: | :--- |
| **System** | `/health` | `GET` | Public | System health check and environment status |
| **Auth** | `/api/v1/auth/signup` | `POST` | Public | Self-registration: creates External Admin + auto-provisions Free workspace |
| **Auth** | `/api/v1/auth/login` | `POST` | Public | OAuth2 password flow; issues JWT Bearer token |
| **Tenants** | `/api/v1/tenants/my-workspace` | `GET` | Authenticated | Fetch active workspace details |
| **Tenants** | `/api/v1/tenants/my-workspace/user-quota` | `GET` | Authenticated | Inspect workspace seat capacity, filled slots, and allowed roles |
| **Tenants** | `/api/v1/tenants/my-workspace/token-usage` | `GET` | Authenticated | Current daily token consumption and remaining quota |
| **Tenants** | `/api/v1/tenants/plans` | `GET` | Authenticated | List all available plan configurations |
| **Tenants** | `/api/v1/tenants/plans` | `POST` | Internal Admin | Create or override a subscription tier config |
| **Permissions** | `/api/v1/permissions/matrix` | `GET` | Authenticated | Complete Plan Tier × Role × Feature access matrix |
| **Permissions** | `/api/v1/permissions/my-access` | `GET` | Authenticated | Current user's effective permissions and assigned capabilities |
| **Permissions** | `/api/v1/permissions/rules` | `GET` / `POST` | Internal Admin | Manage dynamic API route permission rules |
| **Users** | `/api/v1/users/` | `POST` | Workspace Admin | Provision a new team member within seat and role quotas |
| **Users** | `/api/v1/users/` | `GET` | Authenticated | List workspace members (tenant-filtered) |
| **Users** | `/api/v1/users/me` | `GET` | Authenticated | Current authenticated user profile |
| **Documents** | `/api/v1/documents/upload` | `POST` | `documents:upload` | Upload PDF, calculate tokens, generate vector embeddings, store chunks |
| **Documents** | `/api/v1/documents/` | `GET` | `documents:read` | List documents belonging to user's workspace |

---

### Step-by-Step API Usage Walkthrough

#### 1. Public Signup & Workspace Creation
```bash
curl -X POST "http://localhost:8002/api/v1/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "sarah.connor@cyberdyne.com",
    "password": "SecurePassword123!",
    "first_name": "Sarah",
    "last_name": "Connor",
    "phone": "+1234567890",
    "gender": "female",
    "workspace_name": "Cyberdyne AI Labs"
  }'
```

#### 2. Authenticate & Retrieve JWT Token
```bash
curl -X POST "http://localhost:8002/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=sarah.connor@cyberdyne.com&password=SecurePassword123!"
```
*Response:*
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer"
}
```

#### 3. Inspect Workspace Seat & Role Quota
```bash
curl -X GET "http://localhost:8002/api/v1/tenants/my-workspace/user-quota" \
  -H "Authorization: Bearer <TOKEN>"
```
*Response:*
```json
{
  "tenant_id": 1,
  "tenant_name": "Cyberdyne AI Labs",
  "tier": "free",
  "plan_name": "Free Tier",
  "max_users": 1,
  "current_users": 1,
  "remaining_slots": 0,
  "can_create_users": false,
  "allowed_roles_to_assign": ["associate"]
}
```

#### 4. Upload & Vectorize Document
```bash
curl -X POST "http://localhost:8002/api/v1/documents/upload" \
  -H "Authorization: Bearer <TOKEN>" \
  -F "file=@/path/to/quarterly_report.pdf;type=application/pdf"
```
*Response:*
```json
{
  "document_id": 1,
  "file_url": "/static/tenant_1/9d4a8f10-quarterly_report.pdf",
  "tokens_consumed": 2450,
  "daily_tokens_remaining": 47550,
  "message": "Document saved using local storage and vectorized!"
}
```

---

## Technical Documentation Index

For deep architectural analyses, mathematical derivations, database guides, and configuration references, refer to the guides in [`docs/`](file:///docs/README.md):

| Document | Focus & Highlights |
| :--- | :--- |
| [**1. Project Architecture Guide**](file:///docs/project_architecture_guide.md) | Modular Monolith layout, C4 container topology, Cache-Aside pattern, and transaction boundaries. |
| [**2. RAG Architecture Guide**](file:///docs/rag_architecture_guide.md) | `pgvector` vs external vector databases, cosine distance mathematics, chunking heuristics, and multi-tenant isolation. |
| [**3. RAG Workflow Guide**](file:///docs/rag_workflow.md) | End-to-end ingestion pipeline, token estimation formulas, semantic search flow, and generation synthesis. |
| [**4. Plans & Permissions Guide**](file:///docs/plans_and_permissions_guide.md) | Self-signup mechanics, workspace seat quotas, allowed creator/assignable roles, and the dynamic permission matrix. |
| [**5. Layered Workflow Guide**](file:///docs/workflow_api_models_router_repository_schema.md) | Request lifecycle through Routers, Pydantic Schemas, Domain Services, Repositories, and SQLAlchemy Models. |
| [**6. Developer Guide**](file:///docs/developer_guide.md) | Local onboarding handbook, testing tips, extending components, and database migration guidelines. |
| [**7. Free Cloud Databases Guide**](file:///docs/free_cloud_databases_guide.md) | Setting up Neon.tech (`pgvector`), Supabase, Upstash Redis, and Cloudflare R2 at zero monthly cost. |
| [**8. Free Cloud Deployment Guide**](file:///docs/free_deployment_and_environment_guide.md) | Production `.env` configurations and step-by-step deployment to Render.com and cloud platforms. |

---

## Production Security & Best Practices

- **Database Credentials & Connection Pooling**: Production builds should always pass credentials via secure secrets managers. Connection pooling parameters (`pool_size`, `max_overflow`, `pool_recycle`) in `src/core/database.py` should be tuned to match database server hardware.
- **JWT Key Rotation**: Generate a cryptographically robust secret via `openssl rand -hex 32` and avoid committing `.env` to version control.
- **CORS Hardening**: In production environments, replace wildcard origins (`allow_origins=["*"]`) in `src/main.py` with explicit allowed client origins.
- **Relational Integrity**: Vector chunks strictly inherit tenant boundaries through documents via foreign key relationships (`ondelete="CASCADE"`).
- **Alembic Database Migrations**: In production pipelines, disable runtime `Base.metadata.create_all` in `src/main.py` and run deterministic migrations via Alembic:
  ```bash
  alembic revision --autogenerate -m "Migration description"
  alembic upgrade head
  ```

---

## Contributing

We welcome contributions from the community. Please follow these conventions:

1. **Fork the repository** and create a feature branch (`git checkout -b feature/vector-reranking`).
2. **Follow PEP 8 & Typing Standards**: Maintain full type hint coverage compatible with `mypy`.
3. **Format & Lint**: Ensure formatting complies with `black` and `ruff`.
   ```bash
   black src/ tests/
   ruff check src/ tests/
   ```
4. **Execute Tests**: Verify that unit and integration tests pass before opening a PR.
5. **Submit a Pull Request** with a detailed summary of changes and reference relevant issues.

---

## License

This project is licensed under the terms of the **MIT License**.
