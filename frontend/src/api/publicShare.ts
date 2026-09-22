import { apiClient } from "./client";
import type { PublicShare } from "@/types";

export const publicShareApi = {
  // FR-11: no account needed. Send no password first; a protected link answers
  // `requires_password` until the right one is supplied.
  open(token: string, password?: string): Promise<PublicShare> {
    return apiClient.post<PublicShare>(`/public/share/${encodeURIComponent(token)}/access`, {
      password: password ?? null,
    });
  },
};
