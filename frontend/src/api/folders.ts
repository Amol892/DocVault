import { apiClient } from "./client";
import type { Folder } from "@/types";

export const foldersApi = {
  list(workspaceId: string): Promise<Folder[]> {
    return apiClient.get<Folder[]>(`/workspaces/${workspaceId}/folders`);
  },
  create(workspaceId: string, name: string, parentFolderId: string | null): Promise<Folder> {
    return apiClient.post<Folder>(`/workspaces/${workspaceId}/folders`, {
      name,
      parent_folder_id: parentFolderId,
    });
  },
  rename(folderId: string, name: string): Promise<Folder> {
    return apiClient.patch<Folder>(`/folders/${folderId}`, { name });
  },
  delete(folderId: string): Promise<void> {
    return apiClient.delete(`/folders/${folderId}`);
  },
  // Guest-only scoping (folder_grants) — Admin/Owner manage this from the Members page.
  grantAccess(folderId: string, userId: string): Promise<void> {
    return apiClient.post(`/folders/${folderId}/grants`, { user_id: userId });
  },
  revokeAccess(folderId: string, userId: string): Promise<void> {
    return apiClient.delete(`/folders/${folderId}/grants/${userId}`);
  },
};
