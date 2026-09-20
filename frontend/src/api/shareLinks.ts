import { apiClient } from "./client";
import type { ShareLink } from "@/types";

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
  // FR-13: revocation is checked on every access — the API is the source of truth,
  // this call just flips it and the UI reflects the response, never assumes success.
  revoke(linkId: string): Promise<void> {
    return apiClient.delete(`/share-links/${linkId}`);
  },
};
