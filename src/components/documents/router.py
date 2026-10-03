from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.documents.repository import DocumentRepository
from src.components.documents.schemas import DocumentResponse, UploadResponse
from src.components.documents.service import DocumentService
from src.components.tenants.repository import TenantRepository
from src.components.tenants.service import TenantService
from src.components.users.models import User
from src.core.database import get_db
from src.core.deps import get_current_user, RequireFeatureAccess
from src.core.redis import get_redis

router = APIRouter(prefix="/documents", tags=["Documents & RAG"])


def get_document_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> DocumentService:
    # Resolve the dependency tree
    doc_repo = DocumentRepository(session)
    tenant_repo = TenantRepository(session)
    tenant_service = TenantService(tenant_repo, redis)
    return DocumentService(doc_repo, tenant_service)


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    # Gated by Plan & Role permission: documents:upload
    current_user: User = Depends(RequireFeatureAccess("documents:upload")),
    service: DocumentService = Depends(get_document_service),
):
    """Upload a PDF, chunk it, generate embeddings, and store in pgvector."""
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You must belong to a workspace to upload documents.",
        )

    return await service.process_and_upload(
        file=file, tenant_id=current_user.tenant_id, user=current_user
    )


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(
    # Gated by Plan & Role permission: documents:read
    current_user: User = Depends(RequireFeatureAccess("documents:read")),
    service: DocumentService = Depends(get_document_service),
):
    """List all documents belonging to the user's workspace."""
    if not current_user.tenant_id:
        return []
    return await service.get_tenant_documents(current_user.tenant_id)

