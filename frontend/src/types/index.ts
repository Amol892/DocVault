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
  // No email_verified: verification state is not stored (auth_tokens and
  // users.email_verified_at were removed from the schema by decision).
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
}

export interface WorkspaceMember {
  user_id: string;
  name: string;
  email: string;
  role: Role;
  joined_at: string;
  /** Folders a guest has been granted (folder_grants). Only meaningful for role "guest". */
  granted_folder_ids?: string[];
}

export interface WorkspaceInvite {
  id: string;
  email: string;
  role: InvitableRole;
  expires_at: string;
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
  revoked_at: string | null;
  created_at: string;
}

export interface ActivityLogEntry {
  id: string;
  actor_name: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
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
