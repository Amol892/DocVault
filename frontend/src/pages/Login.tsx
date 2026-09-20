import { useState, type FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { ApiClientError } from "@/api/client";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/workspaces");
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <form
        onSubmit={onSubmit}
        style={{
          background: "var(--color-bg-primary)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-md)",
          padding: 32,
          width: "100%",
          maxWidth: 380,
        }}
      >
        <h1 style={{ fontSize: 22, margin: "0 0 4px" }}>DocVault</h1>
        <p style={{ color: "var(--color-text-secondary)", fontSize: 13, margin: "0 0 20px" }}>
          Sign in to your workspaces
        </p>

        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            autoComplete="username"
          />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            autoComplete="current-password"
          />
        </div>

        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
          {submitting ? "Logging in…" : "Log In"}
        </button>
        <Link
          to="/signup"
          style={{ display: "block", textAlign: "center", fontSize: 12, marginTop: 14 }}
        >
          Don't have an account? Sign up
        </Link>
      </form>
    </div>
  );
}
