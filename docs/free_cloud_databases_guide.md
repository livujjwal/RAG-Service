# Zero-Cost Cloud Infrastructure Guide ($0.00/Month)

This guide explains how to connect the **RAG Engine** to 100% free cloud-managed databases, vector stores, Redis caches, and S3-compatible object storage **without rewriting any code**.

---

## 1. Overview & Architecture

The project's architectural abstraction layers ([SQLAlchemy 2.0 Async Engine](file:///c:/Users/admin/Documents/Backup/rag_engine/src/core/database.py), [Async Redis Client](file:///c:/Users/admin/Documents/Backup/rag_engine/src/core/redis.py), and [Storage Factory](file:///c:/Users/admin/Documents/Backup/rag_engine/src/storage/factory.py)) allow you to switch from local Docker containers to cloud providers simply by updating [`.env`](file:///c:/Users/admin/Documents/Backup/rag_engine/.env).

```mermaid
graph LR
    subgraph LocalOrCloudApp ["FastAPI Application (Local Host or Render / Koyeb)"]
        FastAPI["RAG Engine (uvicorn)"]
    end

    subgraph FreeDatabaseProviders ["1. Free Relational + Vector DB ($0/mo)"]
        Neon["Neon.tech (Postgres 16 + pgvector)<br/>0.5 GB Free Serverless"]
        Supabase["Supabase (Postgres + pgvector)<br/>500 MB Free Tier"]
    end

    subgraph FreeCacheProviders ["2. Free Redis Cache & Quotas ($0/mo)"]
        Upstash["Upstash Serverless Redis<br/>10,000 Commands/Day Free"]
    end

    subgraph FreeStorageProviders ["3. Free S3 Document Storage (Optional)"]
        R2["Cloudflare R2 (S3 API)<br/>10 GB Free, Zero Egress Fees"]
    end

    FastAPI -->|DATABASE_URL| Neon
    FastAPI -.->|Alternative DATABASE_URL| Supabase
    FastAPI -->|REDIS_URL (TLS)| Upstash
    FastAPI -.->|STORAGE_BACKEND=s3| R2
```

---

## 2. Free PostgreSQL + pgvector Providers

The application requires PostgreSQL 15+ with the `pgvector` extension enabled. When the app boots, [`lifespan`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/main.py#L36-L52) automatically executes:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```
and automatically creates all tables ([`users`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/components/users/models.py), [`tenants`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/components/tenants/models.py), [`documents`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/components/documents/models.py), [`document_chunks`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/components/documents/models.py)).

---

### Option A: Neon.tech (Recommended)

[Neon](https://neon.tech) provides serverless PostgreSQL with native `pgvector` pre-installed and instant autosuspend to conserve compute.

- **Free Tier Allowance**: 0.5 GB storage, 1 project, unlimited database branches.
- **Credit Card Required**: No.

#### Setup Steps:
1. Sign up at [neon.tech](https://neon.tech).
2. Click **New Project** and name it `rag-engine`.
3. Choose the geographic region closest to your app (e.g., US East, Europe Central).
4. On the project dashboard, locate the **Connection Details** dropdown.
5. Select **Direct connection** (or **Pooled connection** with PgBouncer).
6. Copy the connection URI:
   ```text
   postgresql://user:password@ep-cool-butterfly-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
7. Change the protocol prefix from `postgresql://` to `postgresql+asyncpg://`:
   ```env
   DATABASE_URL=postgresql+asyncpg://user:password@ep-cool-butterfly-123456.us-east-2.aws.neon.tech/neondb
   ```

---

### Option B: Supabase

[Supabase](https://supabase.com) provides managed PostgreSQL with a built-in vector store and full database controls.

- **Free Tier Allowance**: 2 free projects, 500 MB database space, 1 GB file storage.
- **Credit Card Required**: No.

#### Setup Steps:
1. Sign up at [supabase.com](https://supabase.com).
2. Create a new organization and project (e.g., `rag-engine`).
3. Set a strong database password and record it.
4. Go to **Project Settings** > **Database** > **Connection string**.
5. Select **URI** and choose **Session pooler** (port `5432`) or **Transaction pooler** (port `6543`).
6. Supabase provides a string like:
   ```text
   postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
   ```
7. Change the prefix to `postgresql+asyncpg://`:
   ```env
   DATABASE_URL=postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
   ```

---

## 3. Free Serverless Redis Provider: Upstash

[Upstash](https://upstash.com) provides true serverless Redis with automated scaling down to zero.

- **Free Tier Allowance**: 10,000 commands per day, 256 MB data size, 1 database.
- **Used in this project for**:
  - Auth user token cache ([`user_cache:{id}`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/core/deps.py)) with 5-minute TTL.
  - Multi-tenant daily query rate limiting ([`quota:tenant:{id}:date:{YYYY-MM-DD}`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/components/tenants/service.py)) with 24h auto-expiry.
- **Credit Card Required**: No.

#### Setup Steps:
1. Sign up at [upstash.com](https://upstash.com).
2. Click **Create Database**.
3. Choose:
   - **Name**: `rag-engine-redis`
   - **Region**: Same cloud provider/region as your database (minimizes latency).
   - **Type**: Regional.
4. Under the **Details** tab, find the **Node / Python (redis-py)** connection section.
5. Copy the **Redis URL** (starts with `rediss://` for TLS-encrypted connection):
   ```text
   rediss://default:your_secret_token@us1-quick-fox-12345.upstash.io:6379
   ```
6. Set this directly in [`.env`](file:///c:/Users/admin/Documents/Backup/rag_engine/.env):
   ```env
   REDIS_URL=rediss://default:your_secret_token@us1-quick-fox-12345.upstash.io:6379
   ```

> [!NOTE]
> The `rediss://` protocol (with double `s`) signals SSL/TLS encryption. The project's [`redis.asyncio`](file:///c:/Users/admin/Documents/Backup/rag_engine/src/core/redis.py) client automatically negotiates secure TLS with Upstash without needing manual certificate configuration.

---

## 4. Free S3-Compatible Object Storage: Cloudflare R2 (Optional)

When running locally, files are saved to `uploads/` (`STORAGE_BACKEND=local`). However, free cloud hosts (like Render or Koyeb) have ephemeral disks that reset on container restarts.

To retain uploaded PDFs permanently at zero cost, use **Cloudflare R2**:
- **Free Tier Allowance**: 10 GB storage per month, 10 million Class B (read) requests, **zero egress bandwidth fees**.
- **Credit Card Required**: Yes (for identity verification only; no charges under 10 GB).

#### Setup Steps:
1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com) and navigate to **R2**.
2. Click **Create Bucket** (e.g., `rag-engine-uploads`).
3. Click **Manage R2 API Tokens** > **Create API Token** with `Object Read & Write` permissions.
4. Add the following to [`.env`](file:///c:/Users/admin/Documents/Backup/rag_engine/.env):
   ```env
   STORAGE_BACKEND=s3
   AWS_ACCESS_KEY_ID=<your_r2_access_key_id>
   AWS_SECRET_ACCESS_KEY=<your_r2_secret_access_key>
   AWS_REGION_NAME=auto
   S3_BUCKET_NAME=rag-engine-uploads
   AWS_ENDPOINT_URL=https://<your_account_id>.r2.cloudflarestorage.com
   ```

---

## 5. Complete Free Cloud `.env` Template

Copy the snippet below into your [`.env`](file:///c:/Users/admin/Documents/Backup/rag_engine/.env) to run the system entirely against free cloud services:

```env
# ==============================================================================
# RAG Engine - 100% Free Cloud Infrastructure Configuration
# ==============================================================================

# Application Settings
PROJECT_NAME="RAG Engine API"
API_V1_STR="/api/v1"
DEBUG=true

# Database: Neon.tech (PostgreSQL 16 + pgvector)
# Replace with your actual Neon or Supabase async connection string:
DATABASE_URL=postgresql+asyncpg://alex:AbCdEf123456@ep-cool-butterfly-123456.us-east-2.aws.neon.tech/neondb

# Redis: Upstash Serverless Redis (TLS encrypted)
# Replace with your Upstash rediss:// connection string:
REDIS_URL=rediss://default:your_token_here@us1-quick-fox-12345.upstash.io:6379

# Security & JWT Authentication
SECRET_KEY=change-this-to-a-very-long-and-secure-random-secret-key-32chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# AI Provider (OpenAI)
DEFAULT_AI_PROVIDER=openai
OPENAI_API_KEY=sk-proj-your-openai-api-key-here

# File Storage
# For local ephemeral disk:
STORAGE_BACKEND=local
LOCAL_UPLOAD_DIR=uploads

# Optional: Cloudflare R2 / AWS S3
# STORAGE_BACKEND=s3
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
# AWS_REGION_NAME=auto
# S3_BUCKET_NAME=rag-engine-uploads
# AWS_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
```

---

## 6. Verification & Health Check

After updating your [`.env`](file:///c:/Users/admin/Documents/Backup/rag_engine/.env), start the app:

```bash
# Running directly on host
python -m uvicorn src.main:app --host 0.0.0.0 --port 8002 --reload
```

1. **Verify Startup**: Observe console logs. You should see SQLAlchemy connect to Neon, execute `CREATE EXTENSION IF NOT EXISTS vector;`, and initialize tables.
2. **Health Check**: Open [http://localhost:8002/health](http://localhost:8002/health) in your browser.
3. **Docs**: Open [http://localhost:8002/docs](http://localhost:8002/docs) to register users and upload PDFs.
