import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import type { Document } from "@/types";
import { documentsApi } from "@/api/documents";
import { errorMessage } from "@/api/client";
import { Sidebar } from "@/components/Sidebar";
import { VisibilityBadge } from "@/components/VisibilityBadge";
import { UploadModal } from "@/components/UploadModal";
import { ShareLinkModal } from "@/components/ShareLinkModal";
import { useWorkspace } from "@/workspace/WorkspaceContext";
import { can } from "@/permissions/roleHierarchy";
import { useToast } from "@/hooks/useToast";
import { useSafeAction } from "@/hooks/useSafeAction";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";

export function DashboardPage() {
  const { workspaceId = "", folderId } = useParams();
  const { myRole } = useWorkspace();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [shareDoc, setShareDoc] = useState<Document | null>(null);
  const toast = useToast();
  const safe = useSafeAction();
  // one request when typing pauses, not one per keystroke
  const query = useDebouncedValue(search.trim(), 300);

  useEffect(() => {
    // `cancelled` makes a slow, older response unable to overwrite a newer one.
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    documentsApi
      .list({ workspace_id: workspaceId, folder_id: folderId ?? null, q: query || undefined })
      .then((res) => {
        if (!cancelled) setDocuments(res.items);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, folderId, query]);

  function applyVisibilityChange(docId: string, visibility: "workspace" | "public") {
    setDocuments((docs) => docs.map((d) => (d.id === docId ? { ...d, visibility } : d)));
  }

  async function download(doc: Document) {
    const res = await safe(() => documentsApi.getDownloadUrl(doc.id));
    if (res.ok) window.open(res.value, "_blank", "noopener");
  }

  const canUpload = !!myRole && can(myRole, "UPLOAD_DOCUMENT");
  const canShare = !!myRole && can(myRole, "CREATE_SHARE_LINK");

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar workspaceId={workspaceId} />
      <div style={{ flex: 1, padding: "20px 28px", minWidth: 0, overflowX: "auto" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 16,
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <h1 style={{ fontSize: 20, margin: 0 }}>{folderId ? "Folder" : "All Documents"}</h1>
          {canUpload && (
            <button className="btn btn-primary" onClick={() => setUploadOpen(true)}>
              ↑ Upload
            </button>
          )}
        </div>

        <div
          style={{
            background: "var(--color-bg-secondary)",
            borderRadius: "var(--radius-sm)",
            padding: "8px 12px",
            marginBottom: 12,
          }}
        >
          <input
            aria-label="Search documents"
            placeholder="Search by filename, uploader, or folder"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              border: "none",
              background: "transparent",
              outline: "none",
              width: "100%",
              fontSize: 13,
              color: "var(--color-text-primary)",
            }}
          />
        </div>

        {loading && <p style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>Loading…</p>}
        {!loading && loadError && (
          <p className="error-text" role="alert">
            {loadError}
          </p>
        )}
        {!loading && !loadError && documents.length === 0 && (
          <div
            style={{
              textAlign: "center",
              padding: "48px 0",
              color: "var(--color-text-secondary)",
              fontSize: 13,
            }}
          >
            {query ? "No documents match your search." : "No documents here yet."}
            {!query && canUpload ? " Try uploading one." : ""}
          </div>
        )}
        {!loading && !loadError && documents.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 560 }}>
            <thead>
              <tr>
                {["Name", "Visibility", "Owner", "Modified", ""].map((h) => (
                  <th
                    key={h}
                    style={{
                      textAlign: "left",
                      fontSize: 11,
                      fontWeight: 600,
                      color: "var(--color-text-secondary)",
                      padding: "6px 8px",
                      textTransform: "uppercase",
                      letterSpacing: "0.03em",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id} style={{ borderTop: "1px solid var(--color-border)" }}>
                  <td style={{ padding: "10px 8px", fontSize: 13 }}>
                    <span
                      style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 500 }}
                    >
                      📄 {doc.filename}
                    </span>
                  </td>
                  <td style={{ padding: "10px 8px" }}>
                    <VisibilityBadge visibility={doc.visibility} />
                  </td>
                  <td
                    style={{
                      padding: "10px 8px",
                      fontSize: 13,
                      color: "var(--color-text-secondary)",
                    }}
                  >
                    {doc.owner_name}
                  </td>
                  <td
                    style={{
                      padding: "10px 8px",
                      fontSize: 13,
                      color: "var(--color-text-secondary)",
                    }}
                  >
                    {new Date(doc.updated_at).toLocaleDateString()}
                  </td>
                  <td style={{ padding: "10px 8px" }}>
                    <div style={{ display: "flex", gap: 6 }}>
                      {canShare && (
                        <button className="btn btn-ghost" onClick={() => setShareDoc(doc)}>
                          Share
                        </button>
                      )}
                      <button className="btn btn-ghost" onClick={() => download(doc)}>
                        Download
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {uploadOpen && (
        <UploadModal
          workspaceId={workspaceId}
          folderId={folderId ?? null}
          onClose={() => setUploadOpen(false)}
          onUploaded={(doc) => setDocuments((docs) => [doc, ...docs])}
        />
      )}
      {shareDoc && (
        <ShareLinkModal
          document={shareDoc}
          onClose={() => setShareDoc(null)}
          onVisibilityChanged={(id, vis) => {
            applyVisibilityChange(id, vis);
            toast("Visibility updated");
          }}
        />
      )}
    </div>
  );
}
