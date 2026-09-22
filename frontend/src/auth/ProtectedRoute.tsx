import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { VerifyEmailNotice } from "./VerifyEmailNotice";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  // FR-1: nothing else works until the address is confirmed
  if (!user.email_verified) return <VerifyEmailNotice />;
  return <>{children}</>;
}
