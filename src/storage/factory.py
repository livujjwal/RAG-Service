from src.core.config import settings
from src.storage.interfaces import BaseStorageProvider
from src.storage.local_storage import LocalFileStorageProvider


class StorageFactory:
    @staticmethod
    def get_provider() -> BaseStorageProvider:
        """
        Reads the .env configuration and returns the correct storage engine.
        """
        if settings.STORAGE_BACKEND.lower() == "s3":
            # We import this inside the if-statement so the app doesn't crash
            # if aioboto3 isn't installed while you are running locally.
            from src.storage.s3_storage import S3StorageProvider

            return S3StorageProvider()

        # Default to local storage
        return LocalFileStorageProvider()
