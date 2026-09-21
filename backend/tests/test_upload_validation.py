"""The magic-byte, executable and consistency checks applied when an upload is confirmed."""

import pytest

from app.services.upload_validation import check_upload, is_executable, normalize_mime

MAX = 100 * 1024 * 1024
PDF = b"%PDF-1.7\nrest"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 20
GIF = b"GIF89a" + b"\x00" * 20
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 "
ZIP = b"PK\x03\x04" + b"\x00" * 20
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 20
ELF = b"\x7fELF" + b"\x00" * 60
MACHO = b"\xcf\xfa\xed\xfe" + b"\x00" * 60
SHEBANG = b"#!/bin/sh\nrm -rf /\n"


def pe() -> bytes:
    header = bytearray(b"MZ" + b"\x00" * 0x7E)
    header[0x3C:0x40] = (0x40).to_bytes(4, "little")
    header[0x40:0x44] = b"PE\x00\x00"
    return bytes(header)


def check(head: bytes, declared: str, size: int | None = None, stored_type: str | None = None):
    size = len(head) if size is None else size
    return check_upload(
        declared_mime=declared,
        declared_size=size,
        stored_size=size,
        stored_content_type=stored_type or declared,
        head=head,
        max_bytes=MAX,
    )


@pytest.mark.parametrize(
    ("head", "declared"),
    [
        (PDF, "application/pdf"),
        (PNG, "image/png"),
        (JPEG, "image/jpeg"),
        (GIF, "image/gif"),
        (WEBP, "image/webp"),
        (ZIP, "application/zip"),
        (ZIP, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        (ZIP, "application/vnd.oasis.opendocument.text"),
        (OLE, "application/msword"),
        (b"plain text\n", "text/plain"),
        (b"a,b\n1,2\n", "text/csv"),
        (b"{}", "application/json"),
        (b"anything at all", "application/octet-stream"),
        (b"", "text/plain"),
        (PDF, "Application/PDF; charset=binary"),
    ],
)
def test_acceptable_uploads(head: bytes, declared: str) -> None:
    assert check(head, declared) is None


@pytest.mark.parametrize(
    "head",
    [ELF, MACHO, SHEBANG, pe(), b"\xca\xfe\xba\xbe" + b"\x00" * 20],
    ids=lambda h: h[:4].hex(),
)
@pytest.mark.parametrize("declared", ["application/octet-stream", "application/pdf", "text/plain"])
def test_executables_are_refused_whatever_they_claim(head: bytes, declared: str) -> None:
    reason = check(head, declared)
    assert reason is not None
    assert is_executable(head)


def test_a_file_that_merely_starts_with_mz_is_not_an_executable() -> None:
    assert not is_executable(b"MZ is a nice abbreviation, not a program")
    assert check(b"MZ is a nice abbreviation", "text/plain") is None


@pytest.mark.parametrize(
    ("head", "declared"),
    [
        (b"not a pdf", "application/pdf"),
        (b"not a png", "image/png"),
        (PNG, "image/jpeg"),
        (JPEG, "application/pdf"),
        (PDF, "image/png"),
        (ZIP, "application/pdf"),
        (b"not a zip", "application/zip"),
        (b"not a docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        (b"text\x00with a NUL byte", "text/plain"),
        (b"\x00\x01", "application/json"),
    ],
)
def test_content_that_contradicts_the_declared_type(head: bytes, declared: str) -> None:
    assert check(head, declared) is not None


def test_stored_size_must_equal_the_declared_size() -> None:
    reason = check_upload(
        declared_mime="application/pdf",
        declared_size=100,
        stored_size=99,
        stored_content_type="application/pdf",
        head=PDF,
        max_bytes=MAX,
    )
    assert reason is not None and "99" in reason


def test_stored_content_type_must_equal_the_declared_one() -> None:
    assert check(PDF, "application/pdf", stored_type="text/plain") is not None
    assert (
        check_upload(
            declared_mime="application/pdf",
            declared_size=len(PDF),
            stored_size=len(PDF),
            stored_content_type=None,
            head=PDF,
            max_bytes=MAX,
        )
        is not None
    )


def test_oversized_objects_are_refused() -> None:
    reason = check_upload(
        declared_mime="application/pdf",
        declared_size=MAX + 1,
        stored_size=MAX + 1,
        stored_content_type="application/pdf",
        head=PDF,
        max_bytes=MAX,
    )
    assert reason is not None


def test_normalize_mime() -> None:
    assert normalize_mime(" Text/Plain ; charset=UTF-8") == "text/plain"
