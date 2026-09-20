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
  async me(): Promise<User> {
    return apiClient.get<User>("/auth/me");
  },
  logout() {
    setAuthToken(null);
  },
};
