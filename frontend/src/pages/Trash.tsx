import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Sidebar } from "@/components/Sidebar";
import { documentsApi } from "@/api/documents";
import { useWorkspace } from "@/workspace/WorkspaceContext";
import { can } from "@/permissions/roleHierarchy";
import { useToast } from "@/hooks/useToast";
import { useSafeAction } from "@/hooks/useSafeAction";
import type { Document } from "@/types";

// FR-7: deleted documents stay restorable for a grace period, then the purge job removes them.
export function TrashPage() {
  const { workspaceId = "" } = useParams();
  const { myRole } = useWorkspace();
  const toast = useToast();
  const safe = useSafeAction();
  const [items, setItems] = useState<Document[] | null>(null);
  const allowed = !!myRole && can(myRole, "UPLOAD_DOCUMENT");

  const load = useCallback(async () => {
    const res = await safe(() => documentsApi.trash({ workspace_id: workspaceId }));
    if (res.ok) setItems(res.value.items);
  }, [workspaceId, safe]);

  useEffect(() => {
    if (allowed) void load();
  }, [allowed, load]);

  async function restore(doc: Document) {
    const res = await safe(() => documentsApi.restore(doc.id));
    if (!res.ok) return;
    toast(`"${doc.filename}" restored`);
    await load();
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar workspaceId={workspaceId} />
      <div style={{ flex: 1, padding: "20px 28px" }}>
        <h1 style={{ fontSize: 20, margin: "0 0 4px" }}>Trash</h1>
        <p style={{ color: "var(--color-text-secondary)", fontSize: 12, margin: "0 0 16px" }}>
          Deleted documents can be restored for 30 days, then they are removed for good.
        </p>
        {!allowed && (
          <p style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>
            The trash isn't available to Guests.
          </p>
        )}
        {allowed && items === null && <p style={{ fontSize: 13 }}>Loading…</p>}
        {allowed && items?.length === 0 && (
          <p style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>The trash is empty.</p>
        )}
        {items?.map((doc) => (
          <div
            key={doc.id}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              padding: "10px 8px",
              borderTop: "1px solid var(--color-border)",
              fontSize: 13,
            }}
          >
            <span>
              📄 {doc.filename}
              <span style={{ color: "var(--color-text-secondary)", marginLeft: 8 }}>
                deleted {doc.deleted_at ? new Date(doc.deleted_at).toLocaleDateString() : ""}
              </span>
            </span>
            <button className="btn btn-ghost" onClick={() => restore(doc)}>
              Restore
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
