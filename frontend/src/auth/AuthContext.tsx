import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { User } from "@/types";
import { authApi } from "@/api/auth";
import { loadStoredAuthToken, setAuthToken, setUnauthorizedHandler } from "@/api/client";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
  /** re-read the user, e.g. after they confirmed their email in another tab */
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // An expired or revoked token (401 on any authenticated request) drops the session, so
  // ProtectedRoute sends the user back to the login page instead of leaving them on a broken screen.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    return () => setUnauthorizedHandler(null);
  }, []);

  useEffect(() => {
    const token = loadStoredAuthToken();
    if (!token) {
      setLoading(false);
      return;
    }
    authApi
      .me()
      .then(setUser)
      .catch(() => setAuthToken(null))
      .finally(() => setLoading(false));
  }, []);

  async function login(email: string, password: string) {
    const u = await authApi.login(email, password);
    setUser(u);
  }
  async function register(email: string, password: string, name: string) {
    await authApi.register(email, password, name);
    // The account can sign in at once; until the emailed link is opened the API only answers the
    // account endpoints, and ProtectedRoute shows the "confirm your email" screen.
    await login(email, password);
  }
  async function refreshUser() {
    setUser(await authApi.me());
  }
  function logout() {
    // leave immediately; the token is revoked on the server in the background
    setUser(null);
    void authApi.logout();
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
