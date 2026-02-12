import os
import tempfile
from dataclasses import dataclass
from typing import List

import aiofiles
from aiobotocore.session import get_session

from src.config.project_config import settings


@dataclass
class TempFile:
    path: str
    real_name: str

class S3Client:
    def __init__(self, access_key, secret_key, endpoint_url, bucket_name):
        self.config = {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "endpoint_url": endpoint_url,
        }
        self.bucket_name = bucket_name
        self.session = get_session()

    async def download_files(self, file_keys: List[str]) -> List[TempFile]:
        """Скачивает файлы и возвращает список временных путей"""
        result = []

        async with self.session.create_client("s3", **self.config) as client:
            for key in file_keys:
                response = await client.get_object(
                    Bucket=self.bucket_name,
                    Key=key,
                )

                body = response["Body"]
                metadata = response.get("Metadata", {})
                real_name = metadata.get("name")

                if not real_name:
                    real_name = os.path.basename(key)

                suffix = os.path.splitext(real_name)[1]

                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=suffix
                ) as tmp:
                    tmp_path = tmp.name

                async with aiofiles.open(tmp_path, "wb") as f:
                    while chunk := await body.read(1024 * 1024):
                        await f.write(chunk)

                body.close()
                result.append(TempFile(path=tmp_path, real_name=real_name))

        return result


    async def delete_files(self, file_keys: List[str]):
        async with self.session.create_client("s3", **self.config) as client:
            for key in file_keys:
                await client.delete_object(
                    Bucket=self.bucket_name,
                    Key=key,
                )


s3client = S3Client(
    access_key=settings.S3_ACCESS_KEY_ID,
    secret_key=settings.S3_SECRET_ACCESS_KEY,
    endpoint_url=settings.S3_ENDPOINT_URL,
    bucket_name=settings.S3_BUCKET_NAME,
)
