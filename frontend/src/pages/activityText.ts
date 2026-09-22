import type { ActivityLogEntry } from "@/types";

// FR-30: the workspace's audit trail, for Admins and Owners.
const LABELS: Record<string, string> = {
  "workspace.created": "created the workspace",
  "workspace.deleted": "deleted the workspace",
  "member.invited": "invited a member",
  "member.joined": "joined the workspace",
  "member.removed": "removed a member",
  "member.role_changed": "changed a member's role",
  "ownership.transferred": "transferred ownership",
  "guest.document_granted": "gave a guest access to a document",
  "guest.document_revoked": "removed a guest's access to a document",
  "invite.revoked": "revoked an invite",
  "share_link.created": "created a share link",
  "share_link.updated": "changed a share link's settings",
  "share_link.revoked": "revoked a share link",
};

export function describeActivity(entry: ActivityLogEntry): string {
  const base = LABELS[entry.action] ?? entry.action;
  const { from, to } = entry.metadata as { from?: string; to?: string };
  return from && to ? `${base} (${from} → ${to})` : base;
}
