import { useEffect, useState } from "react";
import { Modal } from "./Modal";
import { documentsApi } from "@/api/documents";
import { errorMessage } from "@/api/client";
import type { Document } from "@/types";

// In-app inline viewing for the common types (PDF, images, plain text) — an alternative to
// downloading, for anyone who can already read the document. Everything else stays download-only.
export function PreviewModal({ document, onClose }: { document: Document; onClose: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    documentsApi
      .getPreviewUrl(document.id)
      .then((value) => {
        if (!cancelled) setUrl(value);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [document.id]);

  return (
    <Modal title={document.filename} onClose={onClose} maxWidth={860}>
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {!error && !url && <p style={{ fontSize: 13 }}>Loading…</p>}
      {url && (
        <iframe
          src={url}
          title={document.filename}
          style={{
            width: "100%",
            height: "70vh",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-sm)",
            background: "#fff",
          }}
        />
      )}
    </Modal>
  );
}
