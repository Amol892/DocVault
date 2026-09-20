import { apiClient } from "./client";
import type { Workspace, WorkspaceSummary } from "@/types";

export const workspacesApi = {
  // FR-17: server returns only workspaces the caller belongs to — no client-side
  // filtering is done or should ever be needed here.
  list(): Promise<WorkspaceSummary[]> {
    return apiClient.get<WorkspaceSummary[]>("/workspaces");
  },
  get(workspaceId: string): Promise<Workspace> {
    return apiClient.get<Workspace>(`/workspaces/${workspaceId}`);
  },
  create(name: string): Promise<Workspace> {
    return apiClient.post<Workspace>("/workspaces", { name });
  },
  transferOwnership(workspaceId: string, toUserId: string): Promise<void> {
    return apiClient.post(`/workspaces/${workspaceId}/members/${toUserId}/transfer-ownership`);
  },
  delete(workspaceId: string): Promise<void> {
    return apiClient.delete(`/workspaces/${workspaceId}`);
  },
};
