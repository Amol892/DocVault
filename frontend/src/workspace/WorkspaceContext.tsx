import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Workspace, WorkspaceMember, Role } from "@/types";
import { workspacesApi } from "@/api/workspaces";
import { membersApi } from "@/api/members";
import { errorMessage } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

interface WorkspaceContextValue {
  workspace: Workspace | null;
  members: WorkspaceMember[];
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
  const { user } = useAuth();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refreshMembers() {
    const list = await membersApi.list(workspaceId);
    setMembers(list);
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([workspacesApi.get(workspaceId), membersApi.list(workspaceId)])
      .then(([ws, mem]) => {
        if (cancelled) return;
        setWorkspace(ws);
        setMembers(mem);
      })
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

  const myRole = user ? (members.find((m) => m.user_id === user.id)?.role ?? null) : null;

  return (
    <WorkspaceContext.Provider
      value={{ workspace, members, myRole, loading, error, refreshMembers }}
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
