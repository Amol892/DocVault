import { apiClient } from "./client";
import type { Role, WorkspaceMember, WorkspaceInvite } from "@/types";

export const membersApi = {
  list(workspaceId: string): Promise<WorkspaceMember[]> {
    return apiClient.get<WorkspaceMember[]>(`/workspaces/${workspaceId}/members`);
  },
  invite(workspaceId: string, email: string, role: Role): Promise<WorkspaceInvite> {
    return apiClient.post<WorkspaceInvite>(`/workspaces/${workspaceId}/invites`, { email, role });
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
