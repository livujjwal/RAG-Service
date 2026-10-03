from abc import ABC, abstractmethod
from typing import BinaryIO


class BaseStorageProvider(ABC):
    @abstractmethod
    async def upload_file(
        self, file_obj: BinaryIO, object_name: str, content_type: str
    ) -> str:
        """Uploads a file and returns the public URL or local path."""
        pass
