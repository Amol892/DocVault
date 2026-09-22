import { apiClient, setAuthToken } from "./client";
import type { User } from "@/types";

export interface LoginResponse {
  token: string;
  user: User;
}

export const authApi = {
  async login(email: string, password: string): Promise<User> {
    const res = await apiClient.post<LoginResponse>("/auth/login", { email, password });
    setAuthToken(res.token);
    return res.user;
  },
  async register(email: string, password: string, name: string): Promise<User> {
    return apiClient.post<User>("/auth/register", { email, password, name });
  },
  // FR-1: open the link from the verification email (works once, no session needed)
  verifyEmail(token: string): Promise<void> {
    return apiClient.post("/auth/verify-email", { token });
  },
  resendVerification(): Promise<void> {
    return apiClient.post("/auth/resend-verification");
  },
  // FR-4: always succeeds, whether or not the address has an account
  forgotPassword(email: string): Promise<void> {
    return apiClient.post("/auth/forgot-password", { email });
  },
  resetPassword(token: string, password: string): Promise<void> {
    return apiClient.post("/auth/reset-password", { token, password });
  },
  async me(): Promise<User> {
    return apiClient.get<User>("/auth/me");
  },
  /**
   * Revokes the token on the server (so it stops working even if someone copied it), then forgets
   * it locally. The local session is cleared whether or not the server call succeeds: a user must
   * always be able to sign out, even offline or with an already-expired token.
   */
  async logout(): Promise<void> {
    try {
      await apiClient.post("/auth/logout");
    } catch {
      // best effort: the server may be unreachable, or the token may already be invalid
    } finally {
      setAuthToken(null);
    }
  },
};
