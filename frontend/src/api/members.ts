import { apiClient } from "./client";
import type { Role, WorkspaceMember, WorkspaceInvite } from "@/types";

export const membersApi = {
  list(workspaceId: string): Promise<WorkspaceMember[]> {
    return apiClient.get<WorkspaceMember[]>(`/workspaces/${workspaceId}/members`);
  },
  // a Guest invite can carry the documents they are granted on accepting (FR-21)
  invite(
    workspaceId: string,
    email: string,
    role: Role,
    documentIds: string[] = [],
  ): Promise<WorkspaceInvite> {
    return apiClient.post<WorkspaceInvite>(`/workspaces/${workspaceId}/invites`, {
      email,
      role,
      document_ids: documentIds,
    });
  },
  listInvites(workspaceId: string): Promise<WorkspaceInvite[]> {
    return apiClient.get<WorkspaceInvite[]>(`/workspaces/${workspaceId}/invites`);
  },
  revokeInvite(workspaceId: string, inviteId: string): Promise<void> {
    return apiClient.delete(`/workspaces/${workspaceId}/invites/${inviteId}`);
  },
  changeRole(workspaceId: string, userId: string, role: Role): Promise<void> {
    return apiClient.patch(`/workspaces/${workspaceId}/members/${userId}`, { role });
  },
  remove(workspaceId: string, userId: string): Promise<void> {
    return apiClient.delete(`/workspaces/${workspaceId}/members/${userId}`);
  },
  acceptInvite(token: string): Promise<void> {
    return apiClient.post(`/invites/${token}/accept`);
  },
};
