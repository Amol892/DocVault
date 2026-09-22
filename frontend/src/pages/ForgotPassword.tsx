import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { authApi } from "@/api/auth";
import { errorMessage } from "@/api/client";

// FR-4: ask for a reset link. The answer is the same whether or not the address has an account.
export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await authApi.forgotPassword(email.trim());
      setSent(true);
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
        <h1 style={{ fontSize: 20, margin: "0 0 8px" }}>Reset your password</h1>
        {sent ? (
          <p role="status" style={{ fontSize: 13 }}>
            If an account exists for {email.trim()}, we've sent a link to choose a new password. It
            expires in an hour.
          </p>
        ) : (
          <form onSubmit={onSubmit}>
            <div className="field">
              <label htmlFor="reset-email">Email</label>
              <input
                id="reset-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            {error && (
              <p role="alert" className="error-text">
                {error}
              </p>
            )}
            <button className="btn btn-primary btn-block" disabled={busy}>
              {busy ? "Sending…" : "Send reset link"}
            </button>
          </form>
        )}
        <Link
          to="/login"
          style={{ display: "block", textAlign: "center", fontSize: 12, marginTop: 14 }}
        >
          Back to sign in
        </Link>
      </div>
    </div>
  );
}
