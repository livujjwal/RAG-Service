import io
import os
import uuid

from fastapi import HTTPException, UploadFile, status
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from src.ai.factory import AIFactory
from src.components.documents.repository import DocumentRepository
from src.components.tenants.service import TenantService
from src.components.users.models import User
from src.core.config import settings
from src.storage.factory import StorageFactory


class DocumentService:
    def __init__(self, repository: DocumentRepository, tenant_service: TenantService):
        self.repository = repository
        self.tenant_service = tenant_service
        self.ai_provider = AIFactory.get_provider(...)

        # 1. Ask the Factory for the storage provider!
        # Right now, this returns LocalFileStorageProvider.
        # In the future, you change the .env file and it returns S3StorageProvider.
        self.storage_provider = StorageFactory.get_provider()

    async def process_and_upload(
        self, file: UploadFile, tenant_id: int, user: User
    ) -> dict:
        if not file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are supported.")

        # Read the file into memory
        file_bytes = await file.read()

        # Estimate tokens (approx 1 token per 4 bytes)
        estimated_tokens = max(100, len(file_bytes) // 4)

        # Count & consume token quota for external users; bypass/track for internal
        quota_result = await self.tenant_service.check_and_consume_tokens(
            tenant_id=tenant_id, user=user, tokens=estimated_tokens
        )

        # 2. Upload the file using our Storage Provider
        unique_filename = f"tenant_{tenant_id}/{uuid.uuid4()}-{file.filename}"
        file_stream = io.BytesIO(file_bytes)

        # This will save locally today, but will save to S3 tomorrow!
        file_url = await self.storage_provider.upload_file(
            file_obj=file_stream,
            object_name=unique_filename,
            content_type=file.content_type,
        )

        # 3. Save to Database (including the local file path or S3 URL)
        doc = await self.repository.create_document(
            filename=file.filename,
            file_url=file_url,
            tenant_id=tenant_id,
            uploaded_by=user.id,
        )

        # ... (Run PDF extraction, chunking, and AI pgvector saving here) ...

        return {
            "document_id": doc.id,
            "file_url": file_url,
            "tokens_consumed": estimated_tokens,
            "daily_tokens_remaining": quota_result["remaining_tokens"],
            "message": f"Document saved using {settings.STORAGE_BACKEND} storage and vectorized!",
        }

    async def get_tenant_documents(self, tenant_id: int):
        return await self.repository.list_by_tenant(tenant_id)
