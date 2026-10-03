import os
from typing import BinaryIO

import aiofiles

from src.core.config import settings
from src.storage.interfaces import BaseStorageProvider


class LocalFileStorageProvider(BaseStorageProvider):
    def __init__(self):
        self.upload_dir = settings.LOCAL_UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)

    async def upload_file(
        self,
        file_obj: BinaryIO,
        object_name: str,
        content_type: str = "application/pdf",
    ) -> str:
        # Create full path, including tenant folders (e.g., uploads/tenant_1/file.pdf)
        full_path = os.path.join(self.upload_dir, object_name)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Write file asynchronously to your local hard drive
        async with aiofiles.open(full_path, "wb") as out_file:
            file_obj.seek(0)
            await out_file.write(file_obj.read())

        # Return a relative path that can be served via a static mount later
        return f"/static/{object_name}"
