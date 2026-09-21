import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { WorkspaceSummary } from "@/types";
import { workspacesApi } from "@/api/workspaces";
import { errorMessage } from "@/api/client";
import { RoleBadge } from "@/components/RoleBadge";
import { UserMenu } from "@/components/UserMenu";
import { useToast } from "@/hooks/useToast";
import { useSafeAction } from "@/hooks/useSafeAction";

// FR-17: this list is exactly what GET /workspaces returns — membership-filtered server-side.
// There is no "browse other workspaces" affordance here by design; if it's not in this list,
// the user isn't a member of it.
export function WorkspaceSwitcherPage() {
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const navigate = useNavigate();
  const toast = useToast();
  const safe = useSafeAction();

  const load = useCallback(() => {
    setLoadError(null);
    setWorkspaces(null);
    workspacesApi
      .list()
      .then(setWorkspaces)
      // a failed load is reported as a failure, never as "you have no workspaces"
      .catch((err: unknown) => setLoadError(errorMessage(err)));
  }, []);

  useEffect(load, [load]);

  async function createWorkspace() {
    const name = window.prompt("Name your new workspace:", "New Workspace")?.trim();
    if (!name) return;
    const res = await safe(() => workspacesApi.create(name));
    if (!res.ok) return;
    toast(`Workspace "${res.value.name}" created — you're its Owner`);
    navigate(`/workspaces/${res.value.id}`);
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        justifyContent: "center",
        padding: "40px 24px",
      }}
    >
      <div style={{ maxWidth: 560, width: "100%" }}>
        <div style={{ marginBottom: 16 }}>
          <UserMenu />
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 20,
          }}
        >
          <h1 style={{ fontSize: 20, margin: 0 }}>Your workspaces</h1>
          <button className="btn btn-primary" onClick={createWorkspace}>
            + New workspace
          </button>
        </div>

        {workspaces === null && !loadError && (
          <p style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>Loading…</p>
        )}
        {loadError && (
          <p className="error-text" role="alert">
            {loadError}{" "}
            <button className="btn btn-ghost" onClick={load}>
              Try again
            </button>
          </p>
        )}
        {workspaces?.length === 0 && (
          <p style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>
            You don't belong to any workspaces yet. Create one, or ask a teammate to invite you.
          </p>
        )}
        {workspaces?.map((ws) => (
          <button
            key={ws.id}
            onClick={() => navigate(`/workspaces/${ws.id}`)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: 14,
              width: "100%",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              background: "var(--color-bg-primary)",
              marginBottom: 10,
              textAlign: "left",
            }}
          >
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: 8,
                flexShrink: 0,
                background:
                  ws.role === "guest" ? "var(--color-guest-soft)" : "var(--color-accent-soft)",
              }}
            />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 15 }}>{ws.name}</div>
            </div>
            <RoleBadge role={ws.role} />
          </button>
        ))}
      </div>
    </div>
  );
}
