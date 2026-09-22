import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { authApi } from "@/api/auth";
import { errorMessage } from "@/api/client";

// FR-4: choose a new password with the emailed token.
export function ResetPasswordPage() {
  const { token = "" } = useParams();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("The two passwords don't match.");
      return;
    }
    setBusy(true);
    try {
      await authApi.resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <div
        style={{
          background: "var(--color-bg-primary)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-md)",
          padding: 32,
          width: "100%",
          maxWidth: 380,
        }}
      >
        <h1 style={{ fontSize: 20, margin: "0 0 8px" }}>Choose a new password</h1>
        {done ? (
          <>
            <p role="status" style={{ fontSize: 13 }}>
              Your password was changed. You can sign in with it now.
            </p>
            <Link className="btn btn-primary btn-block" to="/login">
              Sign in
            </Link>
          </>
        ) : (
          <form onSubmit={onSubmit}>
            <div className="field">
              <label htmlFor="new-password">New password</label>
              <input
                id="new-password"
                type="password"
                required
                minLength={8}
                maxLength={128}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="confirm-password">Repeat the password</label>
              <input
                id="confirm-password"
                type="password"
                required
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </div>
            {error && (
              <p role="alert" className="error-text">
                {error}
              </p>
            )}
            <button className="btn btn-primary btn-block" disabled={busy}>
              {busy ? "Saving…" : "Change password"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
