import logging
from typing import BinaryIO

import aioboto3
from botocore.exceptions import ClientError

from src.core.config import settings
from src.storage.interfaces import BaseStorageProvider

logger = logging.getLogger(__name__)


class S3StorageProvider(BaseStorageProvider):
    def __init__(self):
        # Initialize the async boto3 session
        self.session = aioboto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION_NAME,
        )
        self.bucket = settings.S3_BUCKET_NAME
        self.endpoint_url = settings.AWS_ENDPOINT_URL

    async def upload_file(
        self,
        file_obj: BinaryIO,
        object_name: str,
        content_type: str = "application/pdf",
    ) -> str:
        try:
            async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3:
                await s3.upload_fileobj(
                    file_obj,
                    self.bucket,
                    object_name,
                    ExtraArgs={"ContentType": content_type},
                )

            # Construct and return the URL (Assuming public read access or for internal reference)
            return f"https://{self.bucket}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/{object_name}"

        except ClientError as e:
            logger.error(f"Failed to upload to S3: {e}")
            raise Exception("File storage upload failed")

    async def delete_file(self, object_name: str) -> bool:
        try:
            async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3:
                await s3.delete_object(Bucket=self.bucket, Key=object_name)
            return True
        except ClientError as e:
            logger.error(f"Failed to delete from S3: {e}")
            return False
