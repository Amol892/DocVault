"""Which content types are safe to render inline in a browser (an `inline` Content-Disposition),
shared by the public share-link viewer and the in-app document preview. Everything else is only
ever served as a download, never rendered — an uploaded HTML or SVG file can never run as script
on the storage origin.
"""

PREVIEWABLE = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "text/plain",
    }
)
