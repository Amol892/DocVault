import { NavLink, useLocation, useNavigate, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import type { Folder } from "@/types";
import { foldersApi } from "@/api/folders";
import { useAuth } from "@/auth/AuthContext";
import { useWorkspace } from "@/workspace/WorkspaceContext";
import { can, guestCanSeeFolder } from "@/permissions/roleHierarchy";
import { useSafeAction } from "@/hooks/useSafeAction";

// FR-21: folder list is scoped by role. Member/Admin/Owner see every workspace folder; Guest
// sees only folders in their own grant list. This mirrors (never replaces) the server-side
// filtering the API already does.
export function Sidebar({ workspaceId }: { workspaceId: string }) {
  const { user } = useAuth();
  const { workspace, myRole, members } = useWorkspace();
  const navigate = useNavigate();
  const location = useLocation();
  const { folderId } = useParams();
  const safe = useSafeAction();
  const [folders, setFolders] = useState<Folder[]>([]);

  useEffect(() => {
    let cancelled = false;
    safe(() => foldersApi.list(workspaceId)).then((res) => {
      if (!cancelled && res.ok) setFolders(res.value);
    });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, safe]);

  // The grants that apply are the CURRENT USER's, found by user id (not by role: several members
  // can share a role, and a guest must never be shown another guest's folders).
  const me = members.find((m) => m.user_id === user?.id);
  const visibleFolders = folders.filter((f) =>
    myRole ? guestCanSeeFolder(myRole, f.id, me?.granted_folder_ids) : false,
  );

  return (
    <div
      style={{
        width: 250,
        flexShrink: 0,
        background: "var(--color-bg-secondary)",
        padding: "20px 14px",
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      <button
        onClick={() => navigate("/workspaces")}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          padding: "9px 10px",
          background: "var(--color-bg-primary)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-md)",
          fontSize: 13,
          fontWeight: 600,
          marginBottom: 12,
          width: "100%",
        }}
      >
        <span>{workspace?.name ?? "…"}</span>
        <span>⌄</span>
      </button>

      <SidebarLink to={`/workspaces/${workspaceId}`} active={!folderId} label="📄 All Documents" />
      {visibleFolders.map((f) => (
        <SidebarLink
          key={f.id}
          to={`/workspaces/${workspaceId}/folders/${f.id}`}
          active={folderId === f.id}
          label={`📁 ${f.name}`}
          indent={!!f.parent_folder_id}
        />
      ))}

      {myRole && can(myRole, "SEE_MEMBER_LIST") && (
        <>
          <div
            style={{
              fontSize: 10,
              textTransform: "uppercase",
              letterSpacing: "0.04em",
              color: "var(--color-text-secondary)",
              margin: "12px 0 2px 10px",
            }}
          >
            Workspace
          </div>
          <SidebarLink
            to={`/workspaces/${workspaceId}/members`}
            active={location.pathname.endsWith("/members")}
            label="👥 Members & Roles"
          />
        </>
      )}

      {myRole === "guest" && (
        <div
          style={{
            marginTop: "auto",
            background: "var(--color-guest-soft)",
            color: "var(--color-guest)",
            fontSize: 11,
            padding: "8px 10px",
            borderRadius: "var(--radius-sm)",
          }}
        >
          You're a Guest here — you can only see folders that were shared with you.
        </div>
      )}
    </div>
  );
}

function SidebarLink({
  to,
  active,
  label,
  indent,
}: {
  to: string;
  active: boolean;
  label: string;
  indent?: boolean;
}) {
  return (
    <NavLink
      to={to}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "7px 10px",
        borderRadius: "var(--radius-sm)",
        fontSize: 13,
        textDecoration: "none",
        color: active ? "var(--color-accent)" : "var(--color-text-primary)",
        background: active ? "var(--color-accent-soft)" : "transparent",
        fontWeight: active ? 600 : 400,
        paddingLeft: indent ? 26 : 10,
      }}
    >
      {label}
    </NavLink>
  );
}
