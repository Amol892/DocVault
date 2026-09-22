import { useEffect, useState } from "react";
import { Modal } from "./Modal";
import { documentsApi } from "@/api/documents";
import { errorMessage } from "@/api/client";
import { useSafeAction } from "@/hooks/useSafeAction";
import type { Document, DocumentVersion } from "@/types";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// FR-8: every upload is a new version; older ones stay downloadable.
export function VersionsModal({ document, onClose }: { document: Document; onClose: () => void }) {
  const [versions, setVersions] = useState<DocumentVersion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const safe = useSafeAction();

  useEffect(() => {
    let cancelled = false;
    documentsApi
      .versions(document.id)
      .then((list) => {
        if (!cancelled) setVersions(list);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [document.id]);

  async function download(version: DocumentVersion) {
    const res = await safe(() =>
      documentsApi.getVersionDownloadUrl(document.id, version.version_number),
    );
    if (res.ok) window.open(res.value, "_blank", "noopener");
  }

  return (
    <Modal title={`Versions of ${document.filename}`} onClose={onClose} maxWidth={520}>
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {!error && versions === null && <p style={{ fontSize: 13 }}>Loading…</p>}
      {versions?.map((v) => (
        <div
          key={v.version_number}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            padding: "10px 0",
            borderTop: "1px solid var(--color-border)",
            fontSize: 13,
          }}
        >
          <span>
            <strong>Version {v.version_number}</strong>
            {v.is_current ? " (current)" : ""}
            <span style={{ display: "block", color: "var(--color-text-secondary)", fontSize: 12 }}>
              {v.created_by_name} · {new Date(v.created_at).toLocaleString()} ·{" "}
              {formatSize(v.size_bytes)}
            </span>
          </span>
          <button
            className="btn btn-ghost"
            aria-label={`Download version ${v.version_number}`}
            onClick={() => download(v)}
          >
            Download
          </button>
        </div>
      ))}
    </Modal>
  );
}
