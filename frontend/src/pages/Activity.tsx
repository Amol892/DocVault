import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Sidebar } from "@/components/Sidebar";
import { activityApi } from "@/api/activity";
import { useWorkspace } from "@/workspace/WorkspaceContext";
import { can } from "@/permissions/roleHierarchy";
import { useSafeAction } from "@/hooks/useSafeAction";
import { describeActivity } from "@/pages/activityText";
import type { ActivityLogEntry } from "@/types";

const PAGE_SIZE = 50;

export function ActivityPage() {
  const { workspaceId = "" } = useParams();
  const { myRole } = useWorkspace();
  const safe = useSafeAction();
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<ActivityLogEntry[] | null>(null);
  const [total, setTotal] = useState(0);
  const allowed = !!myRole && can(myRole, "VIEW_ACTIVITY_LOG");

  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    safe(() => activityApi.list(workspaceId, page)).then((res) => {
      if (cancelled || !res.ok) return;
      setItems(res.value.items);
      setTotal(res.value.total);
    });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, page, allowed, safe]);

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar workspaceId={workspaceId} />
      <div style={{ flex: 1, padding: "20px 28px" }}>
        <h1 style={{ fontSize: 20, margin: "0 0 16px" }}>Activity</h1>
        {!allowed && (
          <p style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>
            Only Admins and Owners can view the activity log.
          </p>
        )}
        {allowed && items === null && (
          <p style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>Loading…</p>
        )}
        {allowed && items?.length === 0 && (
          <p style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>No activity yet.</p>
        )}
        {items?.map((entry) => (
          <div
            key={entry.id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: 12,
              padding: "10px 8px",
              borderTop: "1px solid var(--color-border)",
              fontSize: 13,
            }}
          >
            <span>
              <strong>{entry.actor_name}</strong> {describeActivity(entry)}
            </span>
            <time
              dateTime={entry.created_at}
              style={{ color: "var(--color-text-secondary)", whiteSpace: "nowrap" }}
            >
              {new Date(entry.created_at).toLocaleString()}
            </time>
          </div>
        ))}
        {allowed && total > PAGE_SIZE && (
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 16 }}>
            <button className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <span style={{ fontSize: 12 }}>
              Page {page} of {pages}
            </span>
            <button className="btn" disabled={page >= pages} onClick={() => setPage(page + 1)}>
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
