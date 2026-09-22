import type { ReactNode } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useParams } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthContext";
import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { WorkspaceProvider, useWorkspace } from "@/workspace/WorkspaceContext";
import { ToastHost } from "@/components/ToastHost";
import { LoginPage } from "@/pages/Login";
import { SignupPage } from "@/pages/Signup";
import { WorkspaceSwitcherPage } from "@/pages/WorkspaceSwitcher";
import { DashboardPage } from "@/pages/Dashboard";
import { MembersRolesPage } from "@/pages/MembersRoles";
import { ActivityPage } from "@/pages/Activity";
import { TrashPage } from "@/pages/Trash";
import { SharedDocumentPage } from "@/pages/SharedDocument";
import { AcceptInvitePage } from "@/pages/AcceptInvite";
import { VerifyEmailPage } from "@/pages/VerifyEmail";
import { ForgotPasswordPage } from "@/pages/ForgotPassword";
import { ResetPasswordPage } from "@/pages/ResetPassword";

// Holds back the page until the workspace and the user's role are known, so no screen ever
// flashes the wrong permissions while loading, and a failed load shows a reason and a way out.
function WorkspaceGate({ children }: { children: ReactNode }) {
  const { loading, error, myRole } = useWorkspace();
  const note = { padding: 24, fontSize: 13, color: "var(--color-text-secondary)" } as const;
  if (loading) return <p style={note}>Loading…</p>;
  if (error || !myRole) {
    return (
      <p style={note} role="alert">
        {error ?? "You're not a member of this workspace."}{" "}
        <Link to="/workspaces">Back to your workspaces</Link>
      </p>
    );
  }
  return <>{children}</>;
}

function WorkspaceScope({ children }: { children: ReactNode }) {
  const { workspaceId } = useParams();
  if (!workspaceId) return <Navigate to="/workspaces" replace />;
  return (
    <WorkspaceProvider workspaceId={workspaceId}>
      <WorkspaceGate>{children}</WorkspaceGate>
    </WorkspaceProvider>
  );
}

function inWorkspace(page: ReactNode) {
  return (
    <ProtectedRoute>
      <WorkspaceScope>{page}</WorkspaceScope>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ToastHost>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            {/* public: a share link works without an account (FR-11) */}
            <Route path="/s/:token" element={<SharedDocumentPage />} />
            <Route path="/invites/:token" element={<AcceptInvitePage />} />
            <Route path="/verify-email/:token" element={<VerifyEmailPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password/:token" element={<ResetPasswordPage />} />

            <Route
              path="/workspaces"
              element={
                <ProtectedRoute>
                  <WorkspaceSwitcherPage />
                </ProtectedRoute>
              }
            />
            <Route path="/workspaces/:workspaceId" element={inWorkspace(<DashboardPage />)} />
            <Route
              path="/workspaces/:workspaceId/folders/:folderId"
              element={inWorkspace(<DashboardPage />)}
            />
            <Route
              path="/workspaces/:workspaceId/members"
              element={inWorkspace(<MembersRolesPage />)}
            />

            <Route path="/workspaces/:workspaceId/trash" element={inWorkspace(<TrashPage />)} />
            <Route
              path="/workspaces/:workspaceId/activity"
              element={inWorkspace(<ActivityPage />)}
            />

            <Route path="/" element={<Navigate to="/workspaces" replace />} />
            <Route path="*" element={<Navigate to="/workspaces" replace />} />
          </Routes>
        </BrowserRouter>
      </ToastHost>
    </AuthProvider>
  );
}
