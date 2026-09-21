// Mirrors docs/06-permission-matrix.md §"Implementation pattern" exactly.
// This is a UX convenience (hide/disable actions the user can't take) — it is
// NOT the authorization boundary. The backend re-checks every one of these
// server-side; nothing here should ever be treated as a security control.
import type { Role } from "@/types";

const ROLE_LEVEL: Record<Role, number> = { owner: 4, admin: 3, member: 2, guest: 1 };

export function roleLevel(role: Role): number {
  return ROLE_LEVEL[role];
}

export function hasLevel(role: Role, minLevel: number): boolean {
  return ROLE_LEVEL[role] >= minLevel;
}

// Action floors — keep these numbers in sync with the backend's ROLE_LEVEL table.
export const ACTION_LEVEL = {
  VIEW_GRANTED_DOCS: 1, // guest+ (still needs the folder-grant check separately)
  UPLOAD_DOCUMENT: 2, // member+
  CREATE_FOLDER: 2, // member+
  CREATE_SHARE_LINK: 2, // member+
  SEE_MEMBER_LIST: 2, // member+
  INVITE_MEMBER: 3, // admin+
  CHANGE_MEMBER_ROLE: 3, // admin+ (plus owner-target guard below)
  REMOVE_MEMBER: 3, // admin+ (plus owner-target guard below)
  GRANT_FOLDER_ACCESS: 3, // admin+
  VIEW_ACTIVITY_LOG: 3, // admin+
  TRANSFER_OWNERSHIP: 4, // owner-only
  DELETE_WORKSPACE: 4, // owner-only
} as const;

export function can(role: Role, action: keyof typeof ACTION_LEVEL): boolean {
  return hasLevel(role, ACTION_LEVEL[action]);
}

// Owner-target protection — an Admin passes CHANGE_MEMBER_ROLE/REMOVE_MEMBER's
// level check but must still be blocked from touching the Owner. Ownership only moves via
// the explicit TRANSFER_OWNERSHIP action.
export function canActOnMember(
  actorRole: Role,
  targetRole: Role,
  action: "CHANGE_MEMBER_ROLE" | "REMOVE_MEMBER",
): boolean {
  if (targetRole === "owner") return false;
  return can(actorRole, action);
}
