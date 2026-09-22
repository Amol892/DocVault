import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Sidebar } from "@/components/Sidebar";
import { RoleBadge } from "@/components/RoleBadge";
import { InviteModal } from "@/components/InviteModal";
import { useWorkspace } from "@/workspace/WorkspaceContext";
import { membersApi } from "@/api/members";
import { workspacesApi } from "@/api/workspaces";
import { documentsApi } from "@/api/documents";
import { can, canActOnMember } from "@/permissions/roleHierarchy";
import { useAuth } from "@/auth/AuthContext";
import { useToast } from "@/hooks/useToast";
import { useSafeAction } from "@/hooks/useSafeAction";
import type { Document, InvitableRole, Role, WorkspaceInvite, WorkspaceMember } from "@/types";

const ASSIGNABLE_ROLES: InvitableRole[] = ["admin", "member", "guest"];

export function MembersRolesPage() {
  const { workspaceId = "" } = useParams();
  const { user } = useAuth();
  const { workspace, members, myRole, refreshMembers } = useWorkspace();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [invites, setInvites] = useState<WorkspaceInvite[]>([]);
  const toast = useToast();
  const safe = useSafeAction();

  // Matrix (PRD 06): Member+ can see the member list; only Admin+ can change or remove anyone.
  const canSee = !!myRole && can(myRole, "SEE_MEMBER_LIST");
  const canManage = !!myRole && can(myRole, "CHANGE_MEMBER_ROLE");

  useEffect(() => {
    if (!canManage) return;
    let cancelled = false;
    safe(() => documentsApi.list({ workspace_id: workspaceId })).then((res) => {
      if (!cancelled && res.ok) setDocuments(res.value.items);
    });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, canManage, safe]);

  // invitations still waiting to be accepted (Admin+)
  const canInvite = !!myRole && can(myRole, "INVITE_MEMBER");
  const loadInvites = useCallback(async () => {
    if (!canInvite) return;
    const res = await safe(() => membersApi.listInvites(workspaceId));
    if (res.ok) setInvites(res.value);
  }, [canInvite, workspaceId, safe]);

  useEffect(() => {
    void loadInvites();
  }, [loadInvites]);

  async function revokeInvite(invite: WorkspaceInvite) {
    const res = await safe(() => membersApi.revokeInvite(workspaceId, invite.id));
    if (!res.ok) return;
    toast(`Invitation for ${invite.email} revoked`);
    await loadInvites();
  }

  const refresh = async () => {
    await safe(refreshMembers);
    await loadInvites();
  };

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

  async function toggleDocumentGrant(member: WorkspaceMember, documentId: string) {
    const has = (member.granted_document_ids ?? []).includes(documentId);
    const res = await safe(() =>
      has
        ? documentsApi.revokeAccess(documentId, member.user_id)
        : documentsApi.grantAccess(documentId, member.user_id),
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
                  {documents.length === 0 && (
                    <span style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>
                      No documents to grant yet
                    </span>
                  )}
                  {documents.map((d) => {
                    const on = (m.granted_document_ids ?? []).includes(d.id);
                    return (
                      <button
                        key={d.id}
                        onClick={() => toggleDocumentGrant(m, d.id)}
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
                        {d.filename}
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
        {canInvite && invites.length > 0 && (
          <section aria-label="Pending invitations" style={{ marginTop: 24 }}>
            <h2 style={{ fontSize: 14, margin: "0 0 8px" }}>Pending invitations</h2>
            {invites.map((invite) => (
              <div
                key={invite.id}
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
                  {invite.email} · {invite.role}
                  <span style={{ color: "var(--color-text-secondary)", marginLeft: 8 }}>
                    {invite.expired
                      ? "expired"
                      : `expires ${new Date(invite.expires_at).toLocaleDateString()}`}
                  </span>
                </span>
                <button className="btn btn-ghost" onClick={() => revokeInvite(invite)}>
                  Revoke
                </button>
              </div>
            ))}
          </section>
        )}
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
