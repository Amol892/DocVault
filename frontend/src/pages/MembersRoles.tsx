import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Sidebar } from "@/components/Sidebar";
import { RoleBadge } from "@/components/RoleBadge";
import { InviteModal } from "@/components/InviteModal";
import { useWorkspace } from "@/workspace/WorkspaceContext";
import { membersApi } from "@/api/members";
import { workspacesApi } from "@/api/workspaces";
import { foldersApi } from "@/api/folders";
import { can, canActOnMember } from "@/permissions/roleHierarchy";
import { useAuth } from "@/auth/AuthContext";
import { useToast } from "@/hooks/useToast";
import { useSafeAction } from "@/hooks/useSafeAction";
import type { Folder, InvitableRole, Role, WorkspaceMember } from "@/types";

const ASSIGNABLE_ROLES: InvitableRole[] = ["admin", "member", "guest"];

export function MembersRolesPage() {
  const { workspaceId = "" } = useParams();
  const { user } = useAuth();
  const { workspace, members, myRole, refreshMembers } = useWorkspace();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [folders, setFolders] = useState<Folder[]>([]);
  const toast = useToast();
  const safe = useSafeAction();

  // Matrix (PRD 06): Member+ can see the member list; only Admin+ can change or remove anyone.
  const canSee = !!myRole && can(myRole, "SEE_MEMBER_LIST");
  const canManage = !!myRole && can(myRole, "CHANGE_MEMBER_ROLE");

  useEffect(() => {
    if (!canManage) return;
    let cancelled = false;
    safe(() => foldersApi.list(workspaceId)).then((res) => {
      if (!cancelled && res.ok) setFolders(res.value);
    });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, canManage, safe]);

  const refresh = () => safe(refreshMembers);

  async function changeRole(member: WorkspaceMember, role: Role) {
    if (!myRole || !canActOnMember(myRole, member.role, "CHANGE_MEMBER_ROLE")) {
      toast("Blocked: you can't change this member's role.");
      return;
    }
    const res = await safe(() => membersApi.changeRole(workspaceId, member.user_id, role));
    if (!res.ok) return;
    toast(`${member.name}'s role changed to ${role}`);
    await refresh();
  }

  async function removeMember(member: WorkspaceMember) {
    if (member.role === "owner") {
      toast("Blocked: a workspace must always have an Owner — transfer ownership first.");
      return;
    }
    if (!myRole || !canActOnMember(myRole, member.role, "REMOVE_MEMBER")) {
      toast("Blocked: you don't have permission to remove this member.");
      return;
    }
    if (
      !window.confirm(
        `Remove ${member.name} from ${workspace?.name}? Their access is revoked immediately.`,
      )
    )
      return;
    const res = await safe(() => membersApi.remove(workspaceId, member.user_id));
    if (!res.ok) return;
    toast(`${member.name} removed — access revoked`);
    await refresh();
  }

  async function transferOwnership(member: WorkspaceMember) {
    if (!myRole || !can(myRole, "TRANSFER_OWNERSHIP")) return;
    if (!window.confirm(`Transfer ownership to ${member.name}? You'll become an Admin.`)) return;
    const res = await safe(() => workspacesApi.transferOwnership(workspaceId, member.user_id));
    if (!res.ok) return;
    toast(`Ownership transferred to ${member.name}`);
    await refresh();
  }

  async function toggleFolderGrant(member: WorkspaceMember, folderId: string) {
    const has = (member.granted_folder_ids ?? []).includes(folderId);
    const res = await safe(() =>
      has
        ? foldersApi.revokeAccess(folderId, member.user_id)
        : foldersApi.grantAccess(folderId, member.user_id),
    );
    if (res.ok) await refresh();
  }

  if (!canSee) {
    return (
      <div style={{ display: "flex", minHeight: "100vh" }}>
        <Sidebar workspaceId={workspaceId} />
        <div style={{ flex: 1, padding: "20px 28px" }}>
          <p style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>
            The member list isn't available to Guests.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar workspaceId={workspaceId} />
      <div style={{ flex: 1, padding: "20px 28px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 16,
          }}
        >
          <h1 style={{ fontSize: 20, margin: 0 }}>{canManage ? "Members & Roles" : "Members"}</h1>
          {myRole && can(myRole, "INVITE_MEMBER") && (
            <button className="btn btn-primary" onClick={() => setInviteOpen(true)}>
              + Invite
            </button>
          )}
        </div>

        {members.map((m) => (
          <div
            key={m.user_id}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 12,
              padding: "12px 8px",
              borderTop: "1px solid var(--color-border)",
            }}
          >
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: 999,
                background: "var(--color-bg-inverse)",
                color: "var(--color-text-inverse)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12,
                fontWeight: 600,
                flexShrink: 0,
              }}
            >
              {initials(m.name)}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 13 }}>
                {m.name}
                {m.user_id === user?.id ? " (you)" : ""}
              </div>
              <div style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>{m.email}</div>
              {canManage && m.role === "guest" && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                  {folders.map((f) => {
                    const on = (m.granted_folder_ids ?? []).includes(f.id);
                    return (
                      <button
                        key={f.id}
                        onClick={() => toggleFolderGrant(m, f.id)}
                        style={{
                          fontSize: 11,
                          padding: "3px 8px",
                          borderRadius: "var(--radius-full)",
                          border: on ? "none" : "1px solid var(--color-border)",
                          background: on ? "var(--color-guest-soft)" : "var(--color-bg-primary)",
                          color: on ? "var(--color-guest)" : "var(--color-text-primary)",
                          fontWeight: on ? 600 : 400,
                        }}
                      >
                        {f.name}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {m.role === "owner" || !canManage ? (
                <RoleBadge role={m.role} />
              ) : (
                <select
                  aria-label={`Role for ${m.name}`}
                  value={m.role}
                  onChange={(e) => changeRole(m, e.target.value as Role)}
                  style={{
                    padding: "6px 8px",
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--color-border)",
                    background: "var(--color-bg-primary)",
                    fontSize: 12,
                  }}
                >
                  {ASSIGNABLE_ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r[0].toUpperCase() + r.slice(1)}
                    </option>
                  ))}
                </select>
              )}
              {m.role === "admin" && myRole && can(myRole, "TRANSFER_OWNERSHIP") && (
                <button className="btn btn-secondary" onClick={() => transferOwnership(m)}>
                  Make Owner
                </button>
              )}
              {canManage && m.role !== "owner" && (
                <button className="btn btn-ghost" onClick={() => removeMember(m)}>
                  Remove
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {inviteOpen && workspace && (
        <InviteModal
          workspaceId={workspaceId}
          workspaceName={workspace.name}
          onClose={() => setInviteOpen(false)}
          onInvited={refresh}
        />
      )}
    </div>
  );
}

function initials(name: string) {
  return name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}
