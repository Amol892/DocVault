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
  move(folderId: string, parentFolderId: string | null): Promise<Folder> {
    return apiClient.patch<Folder>(`/folders/${folderId}`, { parent_folder_id: parentFolderId });
  },
  delete(folderId: string): Promise<void> {
    return apiClient.delete(`/folders/${folderId}`);
  },
};
