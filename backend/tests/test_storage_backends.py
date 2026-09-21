"""The real S3 backend against a real MinIO. Skipped when MinIO is not reachable at S3_ENDPOINT_URL
(start it with `docker compose up -d storage`, which publishes port 9000). Uses its own
`<bucket>-test` bucket so nothing of yours is touched."""

import socket
import uuid
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlsplit

import aioboto3
import httpx
import pytest
from botocore.config import Config

from app.config import get_settings
from app.storage.s3_backend import S3Backend


def _reachable(url: str) -> bool:
    parts = urlsplit(url)
    try:
        with socket.create_connection((parts.hostname or "", parts.port or 80), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture
async def backend() -> AsyncIterator[S3Backend]:
    settings = get_settings()
    if not _reachable(settings.s3_endpoint_url):
        pytest.skip(f"MinIO not reachable at {settings.s3_endpoint_url}")
    bucket = f"{settings.s3_bucket}-test"
    session = aioboto3.Session(
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    async with session.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    ) as client:
        try:
            await client.create_bucket(Bucket=bucket)
        except client.exceptions.BucketAlreadyOwnedByYou:
            pass
    yield S3Backend(
        endpoint_url=settings.s3_endpoint_url,
        public_endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=bucket,
        region=settings.s3_region,
    )


def _key() -> str:
    return f"tests/{uuid.uuid4().hex}/1"


async def test_upload_round_trip(backend: S3Backend) -> None:
    key, data = _key(), b"%PDF-1.7\nhello from the browser"
    url = await backend.presign_upload(
        key, content_type="application/pdf", size_bytes=len(data), expires_seconds=60
    )
    async with httpx.AsyncClient() as http:
        put = await http.put(url, content=data, headers={"Content-Type": "application/pdf"})
    assert put.status_code == 200, put.text

    info = await backend.head(key)
    assert info is not None
    assert info.size_bytes == len(data)
    assert info.content_type == "application/pdf"
    assert await backend.read_prefix(key, 5) == b"%PDF-"

    await backend.delete(key)
    assert await backend.head(key) is None


async def test_head_of_a_missing_object_is_none(backend: S3Backend) -> None:
    assert await backend.head(_key()) is None


async def test_delete_of_a_missing_object_is_fine(backend: S3Backend) -> None:
    await backend.delete(_key())


async def test_wrong_content_type_or_length_is_refused_by_storage(backend: S3Backend) -> None:
    key, data = _key(), b"exactly this"
    url = await backend.presign_upload(
        key, content_type="text/plain", size_bytes=len(data), expires_seconds=60
    )
    async with httpx.AsyncClient() as http:
        wrong_type = await http.put(url, content=data, headers={"Content-Type": "image/png"})
        wrong_length = await http.put(
            url, content=data + b" and more", headers={"Content-Type": "text/plain"}
        )
    assert wrong_type.status_code == 403
    assert wrong_length.status_code == 403
    assert await backend.head(key) is None


async def test_download_url_returns_the_bytes_as_an_attachment(backend: S3Backend) -> None:
    key, data = _key(), b"download me"
    upload = await backend.presign_upload(
        key, content_type="text/plain", size_bytes=len(data), expires_seconds=60
    )
    async with httpx.AsyncClient() as http:
        await http.put(upload, content=data, headers={"Content-Type": "text/plain"})
        url = await backend.presign_download(
            key, filename='r"e/port.txt', content_type="text/plain", expires_seconds=60
        )
        response = await http.get(url)
    assert response.status_code == 200
    assert response.content == data
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment")
    assert "/" not in disposition.split("filename=")[1].split(";")[0]
    await backend.delete(key)


async def test_urls_are_signed_for_the_public_endpoint() -> None:
    settings = get_settings()
    public = "http://files.example.test:9000"
    backend = S3Backend(
        endpoint_url=settings.s3_endpoint_url,
        public_endpoint_url=public,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket="any",
        region=settings.s3_region,
    )
    url = await backend.presign_upload(
        "k/1", content_type="text/plain", size_bytes=3, expires_seconds=900
    )
    parts = urlsplit(url)
    assert parts.netloc == "files.example.test:9000"
    query = parse_qs(parts.query)
    assert query["X-Amz-Expires"] == ["900"]
    signed = query["X-Amz-SignedHeaders"][0].split(";")
    assert "content-type" in signed and "content-length" in signed
    assert backend.object_url("k/1") == f"{settings.s3_endpoint_url.rstrip('/')}/any/k/1"
