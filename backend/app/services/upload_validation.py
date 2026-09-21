"""Basic content validation for uploads (FR-9), applied when the client confirms an upload.

Three independent checks, all on facts the API reads from storage itself (never on what the client
says): the stored size and content type must equal what was declared, executables are refused
whatever they claim to be, and for the common document/image types the first bytes must really look
like the declared type. This is deliberately basic: it is not antivirus.
"""

# (magic bytes at offset 0, kind)
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"PK\x03\x04", "zip"),
    (b"PK\x05\x06", "zip"),  # an empty archive
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole"),  # legacy .doc/.xls/.ppt
    (b"\x1f\x8b", "gzip"),
)

_OCTET = "application/octet-stream"

_COMPATIBLE: dict[str, frozenset[str]] = {
    "pdf": frozenset({"application/pdf"}),
    "png": frozenset({"image/png"}),
    "jpeg": frozenset({"image/jpeg", "image/jpg", "image/pjpeg"}),
    "gif": frozenset({"image/gif"}),
    "webp": frozenset({"image/webp"}),
    "ole": frozenset(
        {
            "application/msword",
            "application/vnd.ms-excel",
            "application/vnd.ms-powerpoint",
            "application/vnd.ms-outlook",
            _OCTET,
        }
    ),
    "gzip": frozenset({"application/gzip", "application/x-gzip", "application/x-tar", _OCTET}),
}

_ZIP_EXACT = frozenset(
    {"application/zip", "application/x-zip-compressed", "application/epub+zip", _OCTET}
)
_ZIP_PREFIXES = (
    "application/vnd.openxmlformats-officedocument.",  # docx, xlsx, pptx
    "application/vnd.oasis.opendocument.",  # odt, ods, odp
)

_LABELS = {
    "pdf": "a PDF",
    "png": "a PNG image",
    "jpeg": "a JPEG image",
    "gif": "a GIF image",
    "webp": "a WebP image",
    "zip": "a ZIP-based file",
    "ole": "a legacy Office file",
    "gzip": "a gzip archive",
}

_TEXT_LIKE = frozenset(
    {"application/json", "application/xml", "application/x-yaml", "application/csv", "text/csv"}
)


def normalize_mime(value: str) -> str:
    """`Text/Plain; charset=UTF-8` -> `text/plain`."""
    return value.split(";", 1)[0].strip().lower()


def _is_windows_executable(head: bytes) -> bool:
    if not head.startswith(b"MZ"):
        return False
    if b"DOS mode" in head[:256] or b"Win32" in head[:256]:
        return True
    if len(head) >= 0x40:
        offset = int.from_bytes(head[0x3C:0x40], "little")
        return 0 < offset < len(head) - 3 and head[offset : offset + 4] == b"PE\x00\x00"
    return False


def is_executable(head: bytes) -> bool:
    """Windows PE, Linux ELF, macOS Mach-O (incl. fat binaries) and shebang scripts."""
    return (
        _is_windows_executable(head)
        or head.startswith(b"\x7fELF")
        or head.startswith((b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe"))
        or head.startswith((b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"))
        or head.startswith(b"#!")
    )


def detect_kind(head: bytes) -> str | None:
    for magic, kind in _SIGNATURES:
        if head.startswith(magic):
            return kind
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "webp"
    return None


def _compatible(kind: str, declared: str) -> bool:
    if kind == "zip":
        return declared in _ZIP_EXACT or declared.startswith(_ZIP_PREFIXES)
    return declared in _COMPATIBLE[kind]


def _requires_signature(declared: str) -> str | None:
    """The content kind a declared type promises, for types verifiable by their first bytes."""
    if declared == "application/pdf":
        return "pdf"
    for kind in ("png", "jpeg", "gif", "webp"):
        if declared in _COMPATIBLE[kind]:
            return kind
    if declared in _ZIP_EXACT - {_OCTET} or declared.startswith(_ZIP_PREFIXES):
        return "zip"
    return None


def check_upload(
    *,
    declared_mime: str,
    declared_size: int,
    stored_size: int,
    stored_content_type: str | None,
    head: bytes,
    max_bytes: int,
) -> str | None:
    """Why this upload must be refused, or None if it is acceptable."""
    declared = normalize_mime(declared_mime)

    if stored_size != declared_size:
        return f"The uploaded file is {stored_size} bytes but {declared_size} were declared."
    if stored_size > max_bytes:
        return f"The uploaded file is larger than the {max_bytes // (1024 * 1024)} MB limit."
    if normalize_mime(stored_content_type or "") != declared:
        return "The file was uploaded with a different content type than the one declared."

    if is_executable(head):
        return "Executable files can't be uploaded."

    kind = detect_kind(head)
    if kind is not None:
        if not _compatible(kind, declared):
            return f"The file is declared as {declared} but its content looks like {_LABELS[kind]}."
        return None

    promised = _requires_signature(declared)
    if promised is not None:
        return (
            f"The file is declared as {declared} "
            f"but its content doesn't look like {_LABELS[promised]}."
        )
    if (declared.startswith("text/") or declared in _TEXT_LIKE) and b"\x00" in head:
        return f"The file is declared as {declared} but contains binary data."
    return None
