# Environment Configuration & Free Demo Deployment Guide

This guide provides a comprehensive reference for configuring environment variables via `.env` and a complete step-by-step walkthrough for deploying the **RAG Engine** to the cloud **100% free of charge** as a live demo.

---

## Part 1: Environment Variables Reference

All application settings are declared and validated in [`src/core/config.py`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/core/config.py) using Pydantic's [`Settings`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/core/config.py#L4-L40) class (`pydantic_settings.BaseSettings`). When the application initializes, it reads from the system environment and falls back to values in a root `.env` file.

### 1.1 Complete Variable Specification

```mermaid
graph TD
    ENV[".env Configuration File"]
    ENV --> CoreConfig["Application & Infrastructure (src/core/config.py)"]
    CoreConfig --> DB["DATABASE_URL (PostgreSQL + asyncpg)"]
    CoreConfig --> Redis["REDIS_URL (Redis Client)"]
    CoreConfig --> Sec["SECRET_KEY & ALGORITHM (JWT Security)"]
    CoreConfig --> AI["OPENAI_API_KEY (AI Factory)"]
    CoreConfig --> Storage["STORAGE_BACKEND & S3 Keys (Storage Factory)"]
```

| Variable | Type | Mandatory? | Default Value | Description & Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `PROJECT_NAME` | `str` | No | `"RAG Engine API"` | Display name shown in Swagger UI (`/docs`), ReDoc (`/redoc`), and OpenAPI metadata. |
| `API_V1_STR` | `str` | No | `"/api/v1"` | URL prefix for all versioned API routes (e.g. `/api/v1/documents`). |
| `DEBUG` | `bool` | No | `False` | Toggles debug mode. When `True`, uvicorn reloads on code edits and returns detailed error responses. |
| `DATABASE_URL` | `str` | **Yes** | `postgresql+asyncpg://...` | Asynchronous database connection string. **Must use the `postgresql+asyncpg://` driver prefix.** |
| `REDIS_URL` | `str` | **Yes** | `redis://localhost:6379/0` | Connection string for Redis. Used for user session caching (`user_cache:*`) and atomic daily tenant quotas (`quota:tenant:*`). |
| `SECRET_KEY` | `str` | **Yes (Prod)** | `"your-super-secret-jwt-key"` | Cryptographic secret used to sign and verify HMAC-SHA256 JWT tokens. |
| `ALGORITHM` | `str` | No | `"HS256"` | JWT token hashing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `int` | No | `10080` (7 days) | Lifetime of issued JWT access tokens in minutes. |
| `DEFAULT_AI_PROVIDER` | `str` | No | `"openai"` | Active AI provider key resolved by [`AIFactory`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/ai/factory.py). |
| `OPENAI_API_KEY` | `str` | **Yes (for RAG)**| `""` | OpenAI API key used for generating 1536-dimensional embeddings (`text-embedding-3-small`) and chat answers (`gpt-4o`). |
| `DEFAULT_AI_API_KEY` | `str` | No | `""` | Optional fallback key when configuring secondary providers (e.g. Anthropic/HuggingFace). |
| `STORAGE_BACKEND` | `str` | No | `"local"` | Storage driver switch: `"local"` for local filesystem or `"s3"` for cloud object storage. |
| `LOCAL_UPLOAD_DIR` | `str` | No | `"uploads"` | Folder where files are stored when `STORAGE_BACKEND="local"`. Mounted as static files at `/static`. |
| `AWS_ACCESS_KEY_ID` | `str` | If using S3 | `None` | AWS access key for S3 bucket operations. |
| `AWS_SECRET_ACCESS_KEY` | `str` | If using S3 | `None` | AWS secret key for S3 bucket operations. |
| `AWS_REGION_NAME` | `str` | No | `"us-east-1"` | AWS S3 bucket region. |
| `S3_BUCKET_NAME` | `str` | If using S3 | `None` | Target S3 bucket name. |
| `AWS_ENDPOINT_URL` | `str` | No | `None` | Custom S3 endpoint URL (for MinIO, Cloudflare R2, or LocalStack). |

---

### 1.2 Ready-to-Use `.env` Templates

#### Template A: Local Hybrid Development (App on Host, DB/Redis in Docker)
```env
PROJECT_NAME="RAG Engine API"
API_V1_STR="/api/v1"
DEBUG=true

# Host mapped ports from docker-compose.yml:
DATABASE_URL=postgresql+asyncpg://postgres:mysecretpassword@localhost:5434/rag_db
REDIS_URL=redis://localhost:6380/0

SECRET_KEY=dev-secret-key-32-characters-minimum-for-security
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

DEFAULT_AI_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-api-key-here

STORAGE_BACKEND=local
LOCAL_UPLOAD_DIR=uploads
```

#### Template B: Full Docker Compose Environment (All Services in Docker)
```env
PROJECT_NAME="RAG Engine API"
API_V1_STR="/api/v1"
DEBUG=true

# Docker network internal hostnames:
DATABASE_URL=postgresql+asyncpg://postgres:mysecretpassword@db:5432/rag_db
REDIS_URL=redis://redis:6379/0

POSTGRES_USER=postgres
POSTGRES_PASSWORD=mysecretpassword
POSTGRES_DB=rag_db

SECRET_KEY=docker-secret-key-32-characters-minimum
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

DEFAULT_AI_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-api-key-here

STORAGE_BACKEND=local
LOCAL_UPLOAD_DIR=/app/uploads
```

---

## Part 2: Free Demo Cloud Deployment Guide

You can deploy the complete stack—FastAPI API, PostgreSQL with `pgvector`, and Redis—online with a public HTTPS URL at **zero cost ($0.00/month)**.

```mermaid
graph LR
    InternetClient["Public Client / Web Browser"] -->|HTTPS| RenderApp["Render.com / Koyeb<br/>(Free Web Service)"]
    RenderApp -->|asyncpg SSL| NeonDB[("Neon.tech<br/>PostgreSQL 16 + pgvector<br/>(Free Tier 0.5 GB)")]
    RenderApp -->|TLS Redis| UpstashRedis[("Upstash Redis<br/>Serverless Redis<br/>(Free 10K requests/day)")]
    RenderApp -->|API| OpenAI["OpenAI API<br/>(text-embedding-3-small & gpt-4o)"]
```

### 2.1 Free Tier Infrastructure Stack

| Component | Free Provider | Plan | Key Capabilities |
| :--- | :--- | :--- | :--- |
| **App Hosting** | [**Render.com**](https://render.com) or [**Koyeb**](https://koyeb.com) | Free Web Service | Automatic deployments from GitHub, free HTTPS, Docker or Python runtime. |
| **Vector Database** | [**Neon.tech**](https://neon.tech) | Free Serverless Postgres | Native PostgreSQL 16 with pre-installed `pgvector`, 0.5 GB storage, zero maintenance. |
| **Cache & Quotas** | [**Upstash**](https://upstash.com) | Serverless Redis | 10,000 commands/day, zero credit card required, instant setup. |

---

### 2.2 Step-by-Step Deployment Instructions

#### Step 1: Provision Free PostgreSQL with `pgvector` on Neon.tech
1. Navigate to [**Neon.tech**](https://neon.tech) and sign up for a free account.
2. Click **Create Project**, name it `rag-engine-demo`, and select the region closest to you.
3. On your project dashboard, find the **Connection Details** box.
4. Copy the connection string. Neon provides a string formatted like:
   ```text
   postgresql://alex:AbCdEf123456@ep-young-mountain-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
5. Convert this string for async SQLAlchemy by changing the prefix from `postgresql://` to `postgresql+asyncpg://`:
   ```text
   postgresql+asyncpg://alex:AbCdEf123456@ep-young-mountain-123456.us-east-2.aws.neon.tech/neondb
   ```
   > [!NOTE]
   > The application's [`lifespan`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/main.py#L36-L51) context manager automatically executes `CREATE EXTENSION IF NOT EXISTS vector;` and generates all database tables on initial startup.

---

#### Step 2: Provision Free Serverless Redis on Upstash
1. Navigate to [**Upstash.com**](https://upstash.com) and create a free account.
2. In the console, click **Create Database**.
3. Choose:
   - **Name**: `rag-engine-redis`
   - **Type**: Regional (select the same cloud region as your Neon database)
   - **Plan**: Free (10K commands/day)
4. Under the **Details** tab, locate the **Redis URL** section.
5. Copy the connection string (format: `rediss://default:your_token@us1-quick-fox-12345.upstash.io:6379`).

---

#### Step 3: Deploy to Render.com
1. Commit your codebase to a **GitHub repository**.
2. Log in to [**Render.com**](https://render.com) and click **New + > Web Service**.
3. Connect your GitHub account and select the repository.
4. Configure the service:
   - **Name**: `rag-engine-demo`
   - **Region**: Choose the region closest to your Neon DB (e.g. Oregon or Frankfurt).
   - **Branch**: `main`
   - **Runtime**: `Docker` (Render automatically uses the [`Dockerfile`](file:///c:/Users/admin/Documents/Backup/rag_engine/Dockerfile)).
     *(Alternatively, choose `Python 3` with Build Command: `pip install -r requirements.txt` and Start Command: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`)*
   - **Instance Type**: `Free` (512 MB RAM, 0.1 CPU).
5. Scroll down to the **Environment Variables** section and add:

| Key | Value | Notes |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@ep-...neon.tech/neondb` | Your Neon async connection string from Step 1 |
| `REDIS_URL` | `rediss://default:...@...upstash.io:6379` | Your Upstash Redis connection string from Step 2 |
| `OPENAI_API_KEY` | `sk-...` | Your OpenAI API key |
| `SECRET_KEY` | *(generate a random 32-character string)* | Used for JWT signing |
| `STORAGE_BACKEND` | `local` | Uses ephemeral container disk for demo uploads |
| `DEBUG` | `false` | Production mode |

6. Click **Create Web Service**. Render will build the container, install packages, run lifespan table setup, and expose a live HTTPS URL.

---

#### Step 4: Verify and Test the Demo
Once Render completes the build, your API will be live at:
`https://rag-engine-demo.onrender.com`

1. **Verify Healthcheck**:
   Navigate to `https://rag-engine-demo.onrender.com/health` in your browser. It should return:
   ```json
   {
     "status": "healthy",
     "environment": "production"
   }
   ```
2. **Access Interactive Swagger Documentation**:
   Open `https://rag-engine-demo.onrender.com/docs` to test endpoints interactively.
3. **Register an Admin User**:
   Send a `POST` request to `/api/v1/users/` with `user_role: "admin"` to establish the primary account.
4. **Log in & Test RAG Upload**:
   - Call `POST /api/v1/auth/login` to obtain an access token.
   - Click the green **Authorize** button in Swagger UI and paste `Bearer <your_token>`.
   - Call `POST /api/v1/documents/upload` to upload a PDF. Verify that it chunks the document, generates embeddings via OpenAI, and saves vectors to Neon `pgvector`.

---

### 2.3 Free-Tier Caveats & Best Practices

- **Render Cold Starts**: On Render's free tier, containers spin down after 15 minutes of inactivity. The first request after sleep may take ~30–50 seconds while the instance boots.
- **Local Storage Ephemeral Disk**: When `STORAGE_BACKEND=local`, files stored in `uploads/` will be reset if Render restarts the free container. For persistent document storage in production, switch to an AWS S3 bucket or a free Cloudflare R2 bucket (10 GB free) by setting `STORAGE_BACKEND=s3`.
- **Neon Connection Limits**: Free Neon projects allow up to 100 concurrent connections. If scaling, use Neon's pooled connection string (port 6543 with `pgbouncer`).
