import { apiClient } from "./client";
import type { Paginated, ShareAccessLogEntry, ShareLink } from "@/types";

interface CreateShareLinkInput {
  expires_at?: string | null;
  password?: string | null;
  allow_download: boolean;
}

export const shareLinksApi = {
  list(documentId: string): Promise<ShareLink[]> {
    return apiClient.get<ShareLink[]>(`/documents/${documentId}/share-links`);
  },
  create(documentId: string, input: CreateShareLinkInput): Promise<ShareLink> {
    return apiClient.post<ShareLink>(`/documents/${documentId}/share-links`, input);
  },
  // The only setting changeable after creation — the address itself never changes.
  updateAllowDownload(linkId: string, allowDownload: boolean): Promise<ShareLink> {
    return apiClient.patch<ShareLink>(`/share-links/${linkId}`, { allow_download: allowDownload });
  },
  // FR-14: who opened the link and when
  accessLog(linkId: string): Promise<Paginated<ShareAccessLogEntry>> {
    return apiClient.get<Paginated<ShareAccessLogEntry>>(`/share-links/${linkId}/access-log`);
  },
  // FR-13: revocation is checked on every access — the API is the source of truth,
  // this call just flips it and the UI reflects the response, never assumes success.
  revoke(linkId: string): Promise<void> {
    return apiClient.delete(`/share-links/${linkId}`);
  },
};
