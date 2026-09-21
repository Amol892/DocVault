"""MinIO / S3 implementation of StorageBackend (aioboto3, SigV4, path-style addressing).

Two addresses are involved:
  * `endpoint_url`: what the API itself uses for HEAD / ranged GET / DELETE (Docker: storage:9000);
  * `public_endpoint_url`: what the BROWSER can reach; pre-signed URLs are signed for this host,
    because a SigV4 signature covers the Host header.
"""

from typing import Any

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.storage.base import ObjectInfo, content_disposition

_NOT_FOUND = {"404", "NoSuchKey", "NotFound"}


class S3Backend:
    def __init__(
        self,
        *,
        endpoint_url: str,
        public_endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
    ) -> None:
        self._endpoint = endpoint_url.rstrip("/")
        self._public_endpoint = public_endpoint_url.rstrip("/")
        self._bucket = bucket
        self._session = aioboto3.Session(
            aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name=region
        )
        self._config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 2},
            connect_timeout=5,
            read_timeout=15,
        )

    def _client(self, endpoint_url: str) -> Any:
        return self._session.client("s3", endpoint_url=endpoint_url, config=self._config)

    async def presign_upload(
        self, key: str, *, content_type: str, size_bytes: int, expires_seconds: int
    ) -> str:
        # ContentType and ContentLength are part of the signature: the browser must send exactly
        # what was declared. (confirm-upload still verifies the stored object; that is the control.)
        async with self._client(self._public_endpoint) as s3:
            url: str = await s3.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "ContentType": content_type,
                    "ContentLength": size_bytes,
                },
                ExpiresIn=expires_seconds,
                HttpMethod="PUT",
            )
        return url

    async def presign_download(
        self, key: str, *, filename: str, content_type: str, expires_seconds: int
    ) -> str:
        async with self._client(self._public_endpoint) as s3:
            url: str = await s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "ResponseContentType": content_type,
                    "ResponseContentDisposition": content_disposition(filename),
                },
                ExpiresIn=expires_seconds,
            )
        return url

    async def head(self, key: str) -> ObjectInfo | None:
        async with self._client(self._endpoint) as s3:
            try:
                response = await s3.head_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in _NOT_FOUND:
                    return None
                raise
        return ObjectInfo(
            size_bytes=int(response["ContentLength"]), content_type=response.get("ContentType")
        )

    async def read_prefix(self, key: str, length: int) -> bytes:
        async with self._client(self._endpoint) as s3:
            response = await s3.get_object(
                Bucket=self._bucket, Key=key, Range=f"bytes=0-{max(length - 1, 0)}"
            )
            body: bytes = await response["Body"].read()
        return body

    async def delete(self, key: str) -> None:
        async with self._client(self._endpoint) as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)

    def object_url(self, key: str) -> str:
        return f"{self._endpoint}/{self._bucket}/{key}"
