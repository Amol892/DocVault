import { apiClient } from "./client";
import type { InvitePreview } from "@/types";

export const invitesApi = {
  // no account needed: the token in the link is the credential
  preview(token: string): Promise<InvitePreview> {
    return apiClient.get<InvitePreview>(`/invites/${encodeURIComponent(token)}`);
  },
};
