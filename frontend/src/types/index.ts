// Types mirror the DocVault API (PRD/10-api-specification.md) and the database schema
// (PRD/04-database-schema.md). Update them in the same change as the API.
// Ids are opaque random strings (12-char base62), never assumed to be UUIDs or sortable.

export type Role = "owner" | "admin" | "member" | "guest";
/** Roles an invite can carry: ownership only moves by transfer, never by invite. */
export type InvitableRole = Exclude<Role, "owner">;

export interface User {
  id: string;
  email: string;
  name: string;
  /** FR-1: false until the emailed link is opened; the API refuses everything else meanwhile */
  email_verified: boolean;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  role: Role;
}

export interface Workspace {
  id: string;
  name: string;
  owner_id: string;
  created_at: string;
  /** The caller's own role. Guests cannot list members, so this is how every role learns theirs. */
  my_role: Role;
}

export interface WorkspaceMember {
  user_id: string;
  name: string;
  email: string;
  role: Role;
  joined_at: string;
  /** Documents a guest has been granted (document_grants, FR-21). Only meaningful for "guest". */
  granted_document_ids?: string[];
}

export interface WorkspaceInvite {
  id: string;
  email: string;
  role: InvitableRole;
  expires_at: string;
  created_at: string;
  expired: boolean;
  /** only in the response that creates the invite (the server keeps just a hash of the token) */
  url?: string;
  /** whether the invitation email went out; when false, hand `url` over yourself */
  email_sent?: boolean;
}

/** What the holder of an invitation link sees before accepting. */
export interface InvitePreview {
  workspace_name: string;
  role: InvitableRole;
  email: string;
  expired: boolean;
}

export interface Folder {
  id: string;
  workspace_id: string | null;
  parent_folder_id: string | null;
  name: string;
}

/** Derived by the API: "private" (personal), "workspace", or "public" (has an active share link). */
export type DocumentVisibility = "private" | "workspace" | "public";

export interface Document {
  id: string;
  owner_id: string;
  owner_name: string;
  workspace_id: string | null;
  folder_id: string | null;
  filename: string;
  /** mime_type and size_bytes come from the document's latest version (highest version_number). */
  mime_type: string;
  size_bytes: number;
  visibility: DocumentVisibility;
  /** Soft delete: null while the document is live. */
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ShareLink {
  id: string;
  document_id: string;
  /**
   * The full public URL. Only present in the response that CREATES the link: the server keeps just a
   * hash of the token, so the URL cannot be shown again afterwards.
   */
  url?: string;
  allow_download: boolean;
  has_password: boolean;
  expires_at: string | null;
  /** the expiry date has passed (the link no longer works) */
  expired: boolean;
  revoked_at: string | null;
  created_at: string;
}

export interface ActivityLogEntry {
  id: string;
  actor_id: string;
  actor_name: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ApiError {
  error: { code: string; message: string };
}

export interface Paginated<T> {
  items: T[];
  page: number;
  total: number;
}

export interface DocumentVersion {
  version_number: number;
  size_bytes: number;
  mime_type: string;
  created_by_name: string;
  created_at: string;
  is_current: boolean;
}

export interface ShareAccessLogEntry {
  accessed_at: string;
  ip_address: string | null;
  user_agent: string | null;
  outcome: "ok" | "bad_password" | "expired" | "revoked";
}

/** What a link recipient gets (FR-15): one document's details and short-lived URLs, nothing else. */
export interface PublicShare {
  requires_password: boolean;
  filename: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  allow_download: boolean | null;
  expires_at: string | null;
  download_url: string | null;
  preview_url: string | null;
}
