import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { authApi } from "@/api/auth";
import { errorMessage } from "@/api/client";

// FR-1: the page the emailed link opens. No session needed: the token is the credential.
export function VerifyEmailPage() {
  const { token = "" } = useParams();
  const [state, setState] = useState<"working" | "done" | "failed">("working");
  const [error, setError] = useState<string | null>(null);
  // A token works once. React StrictMode runs effects twice in development, and the second
  // request would report the link as used, so only the first is sent.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    authApi
      .verifyEmail(token)
      .then(() => setState("done"))
      .catch((err: unknown) => {
        setError(errorMessage(err));
        setState("failed");
      });
  }, [token]);

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
      {state === "working" && <p style={{ fontSize: 13 }}>Confirming your email…</p>}
      {state === "done" && (
        <>
          <h1 style={{ fontSize: 18, marginTop: 0 }}>Email confirmed</h1>
          <p style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
            Thank you. You can use DocVault now.
          </p>
          <Link className="btn btn-primary" to="/workspaces">
            Continue
          </Link>
        </>
      )}
      {state === "failed" && (
        <>
          <h1 style={{ fontSize: 18, marginTop: 0 }}>This link can't be used</h1>
          <p role="alert" style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
            {error} Sign in and ask for a new confirmation email.
          </p>
          <Link className="btn btn-secondary" to="/login">
            Sign in
          </Link>
        </>
      )}
    </main>
  );
}
