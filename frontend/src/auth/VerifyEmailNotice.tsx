import { useState } from "react";
import { authApi } from "@/api/auth";
import { errorMessage } from "@/api/client";
import { useAuth } from "./AuthContext";

// FR-1: shown instead of the app while the signed-in user's email is not confirmed yet.
export function VerifyEmailNotice() {
  const { user, logout, refreshUser } = useAuth();
  const [message, setMessage] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function resend() {
    setBusy(true);
    setProblem(null);
    setMessage(null);
    try {
      await authApi.resendVerification();
      setMessage("A new confirmation email is on its way.");
    } catch (err) {
      setProblem(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function check() {
    setBusy(true);
    setProblem(null);
    setMessage(null);
    try {
      await refreshUser();
      // a confirmed user never reaches this screen again; if we are still here, it isn't yet
      setMessage("Not confirmed yet. Open the link in the email first.");
    } catch (err) {
      setProblem(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main
      style={{
        maxWidth: 440,
        margin: "80px auto",
        padding: 24,
        background: "var(--color-bg-primary)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-md)",
      }}
    >
      <h1 style={{ fontSize: 18, marginTop: 0 }}>Confirm your email address</h1>
      <p style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
        We sent a confirmation link to <strong>{user?.email}</strong>. Open it to start using
        DocVault.
      </p>
      {message && (
        <p role="status" style={{ fontSize: 13 }}>
          {message}
        </p>
      )}
      {problem && (
        <p role="alert" className="error-text">
          {problem}
        </p>
      )}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn btn-primary" onClick={check} disabled={busy}>
          I've confirmed it
        </button>
        <button className="btn btn-secondary" onClick={resend} disabled={busy}>
          Resend email
        </button>
        <button className="btn btn-ghost" onClick={logout}>
          Sign out
        </button>
      </div>
    </main>
  );
}
