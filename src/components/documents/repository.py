from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.documents.models import Document, DocumentChunk


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_document(
        self, filename: str, file_url: str, tenant_id: int, uploaded_by: int
    ) -> Document:
        doc = Document(
            filename=filename,
            file_url=file_url,
            tenant_id=tenant_id,
            uploaded_by=uploaded_by,
        )
        self.session.add(doc)
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def save_chunks(self, chunks_data: list[dict]):
        """Bulk insert for massive performance gains when uploading large PDFs."""
        chunks = [DocumentChunk(**data) for data in chunks_data]
        self.session.add_all(chunks)
        await self.session.commit()

    async def list_by_tenant(self, tenant_id: int) -> Sequence[Document]:
        result = await self.session.execute(
            select(Document).where(Document.tenant_id == tenant_id)
        )
        return result.scalars().all()
