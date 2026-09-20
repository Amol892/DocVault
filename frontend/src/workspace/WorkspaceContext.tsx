import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Workspace, WorkspaceMember, Role } from "@/types";
import { workspacesApi } from "@/api/workspaces";
import { membersApi } from "@/api/members";
import { errorMessage } from "@/api/client";
import { can } from "@/permissions/roleHierarchy";

interface WorkspaceContextValue {
  workspace: Workspace | null;
  members: WorkspaceMember[];
  /** The signed-in user's role here, as reported by the API (works for Guests too). */
  myRole: Role | null;
  loading: boolean;
  /** Set when the workspace could not be loaded (not a member, deleted, network...). */
  error: string | null;
  refreshMembers: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

export function WorkspaceProvider({
  workspaceId,
  children,
}: {
  workspaceId: string;
  children: ReactNode;
}) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refreshMembers() {
    if (!workspace || !can(workspace.my_role, "SEE_MEMBER_LIST")) return;
    setMembers(await membersApi.list(workspaceId));
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      const ws = await workspacesApi.get(workspaceId);
      // The role comes with the workspace. The member list is only fetched by roles allowed to
      // see it: a Guest gets 403 there, and must still be able to open the workspace.
      const list = can(ws.my_role, "SEE_MEMBER_LIST") ? await membersApi.list(workspaceId) : [];
      if (cancelled) return;
      setWorkspace(ws);
      setMembers(list);
    })()
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  return (
    <WorkspaceContext.Provider
      value={{
        workspace,
        members,
        myRole: workspace?.my_role ?? null,
        loading,
        error,
        refreshMembers,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}
