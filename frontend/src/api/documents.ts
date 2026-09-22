import { apiClient } from "./client";
import type { Document, DocumentVersion, Paginated } from "@/types";

interface UploadUrlResponse {
  upload_url: string;
  storage_key: string;
  document_id: string;
}
interface DownloadUrlResponse {
  download_url: string;
  expires_in: number;
}

export const documentsApi = {
  list(params: {
    workspace_id?: string;
    folder_id?: string | null;
    q?: string;
    page?: number;
  }): Promise<Paginated<Document>> {
    return apiClient.get<Paginated<Document>>("/documents", {
      workspace_id: params.workspace_id,
      folder_id: params.folder_id ?? undefined,
      q: params.q,
      page: params.page,
    });
  },

  // FR-5/6: request a pre-signed URL, PUT the file bytes directly to storage,
  // then confirm — the API server never buffers the file itself.
  async upload(
    file: File,
    opts: { workspaceId?: string; folderId?: string | null; documentId?: string },
  ): Promise<Document> {
    // The pre-signed URL is signed for the content type declared here, so the PUT must send the
    // exact same value (a file with no MIME type would otherwise fail the storage signature check).
    const contentType = file.type || "application/octet-stream";
    const { upload_url, document_id } = await apiClient.post<UploadUrlResponse>(
      "/documents/upload-url",
      {
        filename: file.name,
        mime_type: contentType,
        size_bytes: file.size,
        workspace_id: opts.workspaceId ?? null,
        folder_id: opts.folderId ?? null,
        // set to add a new version to an existing document
        document_id: opts.documentId ?? null,
      },
    );

    const putRes = await fetch(upload_url, {
      method: "PUT",
      body: file,
      headers: { "Content-Type": contentType },
    });
    if (!putRes.ok) throw new Error("Upload to storage failed");

    return apiClient.post<Document>(`/documents/${document_id}/confirm-upload`);
  },

  async getDownloadUrl(documentId: string): Promise<string> {
    const res = await apiClient.get<DownloadUrlResponse>(`/documents/${documentId}/download-url`);
    return res.download_url;
  },
  async getPreviewUrl(documentId: string): Promise<string> {
    const res = await apiClient.get<{ preview_url: string; expires_in: number }>(
      `/documents/${documentId}/preview-url`,
    );
    return res.preview_url;
  },

  // FR-7: recently deleted documents (Members and above) and undoing a delete
  trash(params: { workspace_id?: string; page?: number }): Promise<Paginated<Document>> {
    return apiClient.get<Paginated<Document>>("/documents/trash", {
      workspace_id: params.workspace_id,
      page: params.page,
    });
  },
  restore(documentId: string): Promise<Document> {
    return apiClient.post<Document>(`/documents/${documentId}/restore`);
  },

  // FR-8: version history
  versions(documentId: string): Promise<DocumentVersion[]> {
    return apiClient.get<DocumentVersion[]>(`/documents/${documentId}/versions`);
  },
  async getVersionDownloadUrl(documentId: string, versionNumber: number): Promise<string> {
    const res = await apiClient.get<DownloadUrlResponse>(
      `/documents/${documentId}/versions/${versionNumber}/download-url`,
    );
    return res.download_url;
  },

  rename(documentId: string, filename: string): Promise<Document> {
    return apiClient.patch<Document>(`/documents/${documentId}`, { filename });
  },
  move(documentId: string, folderId: string | null): Promise<Document> {
    return apiClient.patch<Document>(`/documents/${documentId}`, { folder_id: folderId });
  },
  softDelete(documentId: string): Promise<void> {
    return apiClient.delete(`/documents/${documentId}`);
  },

  // FR-21: Guest access is granted per document — Admin/Owner manage this from the Members page.
  grantAccess(documentId: string, userId: string): Promise<void> {
    return apiClient.post(`/documents/${documentId}/grants`, { user_id: userId });
  },
  revokeAccess(documentId: string, userId: string): Promise<void> {
    return apiClient.delete(`/documents/${documentId}/grants/${userId}`);
  },
};
