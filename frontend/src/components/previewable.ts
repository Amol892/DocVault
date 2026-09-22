// Mirrors the backend's PREVIEWABLE set (app/services/preview.py): formats a browser can render
// inline without running anything from the file. Everything else is download-only.
const PREVIEWABLE_MIME_TYPES = new Set([
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
  "text/plain",
]);

export function isPreviewable(mimeType: string): boolean {
  return PREVIEWABLE_MIME_TYPES.has(mimeType);
}
