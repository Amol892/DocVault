import { useState, type FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { ApiClientError } from "@/api/client";

export function SignupPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register(email, password, name);
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
        <h1 style={{ fontSize: 22, margin: "0 0 4px" }}>Create your account</h1>
        <p style={{ color: "var(--color-text-secondary)", fontSize: 13, margin: "0 0 20px" }}>
          Use your work email. You can create or join a workspace right after signing up.
        </p>

        <div className="field">
          <label htmlFor="name">Full name</label>
          <input
            id="name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Jordan Lee"
            autoComplete="name"
          />
        </div>
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
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            autoComplete="new-password"
          />
        </div>

        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </button>
        <Link
          to="/login"
          style={{ display: "block", textAlign: "center", fontSize: 12, marginTop: 14 }}
        >
          Already have an account? Log in
        </Link>
      </form>
    </div>
  );
}
