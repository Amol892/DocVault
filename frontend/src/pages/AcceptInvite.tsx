import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { invitesApi } from "@/api/invites";
import { membersApi } from "@/api/members";
import { errorMessage } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { useToast } from "@/hooks/useToast";
import type { InvitePreview } from "@/types";

// FR-18: the page an invitation link opens. Someone without an account signs up first (with the
// invited email), then comes back here to accept.
export function AcceptInvitePage() {
  const { token = "" } = useParams();
  const { user, loading: authLoading, logout } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [invite, setInvite] = useState<InvitePreview | null>(null);
  // A broken link (unknown/expired/revoked/already used): nothing more to do here.
  const [loadError, setLoadError] = useState<string | null>(null);
  // A failed accept attempt: shown alongside the invite, which stays fixable (e.g. sign out and
  // sign in with the right account) rather than replacing the whole page.
  const [acceptError, setAcceptError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    invitesApi
      .preview(token)
      .then((preview) => {
        if (!cancelled) setInvite(preview);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function accept() {
    setAccepting(true);
    setAcceptError(null);
    try {
      await membersApi.acceptInvite(token);
      toast(`You joined ${invite?.workspace_name ?? "the workspace"}`);
      navigate("/workspaces");
    } catch (err) {
      setAcceptError(errorMessage(err));
    } finally {
      setAccepting(false);
    }
  }

  const card = {
    maxWidth: 440,
    margin: "80px auto",
    padding: 24,
    background: "var(--color-bg-primary)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
  } as const;
  const next = encodeURIComponent(`/invites/${token}`);

  if (loadError) {
    return (
      <main style={card}>
        <h1 style={{ fontSize: 18, marginTop: 0 }}>This invitation can't be used</h1>
        <p role="alert" style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
          {loadError}
        </p>
        <Link to="/workspaces">Go to your workspaces</Link>
      </main>
    );
  }
  if (!invite || authLoading) {
    return (
      <main style={card}>
        <p style={{ fontSize: 13 }}>Loading…</p>
      </main>
    );
  }

  const wrongAccount = !!user && user.email.toLowerCase() !== invite.email.toLowerCase();
  const unverified = !!user && !wrongAccount && !user.email_verified;
  const canAccept = !!user && !wrongAccount && !unverified;

  return (
    <main style={card}>
      <h1 style={{ fontSize: 18, marginTop: 0 }}>Join {invite.workspace_name}</h1>
      <p style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
        You were invited as <strong>{invite.role}</strong> with the email{" "}
        <strong>{invite.email}</strong>.
      </p>

      {wrongAccount && (
        <>
          <p role="alert" className="error-text">
            You're signed in as {user.email}, but this invitation is for {invite.email}. Sign out
            and sign in with that account to accept it.
          </p>
          <button className="btn btn-secondary" onClick={logout}>
            Sign out
          </button>
        </>
      )}

      {unverified && (
        <p role="alert" className="error-text">
          Confirm your email address before accepting. Check your inbox for the confirmation link,
          or sign in again to resend it.
        </p>
      )}

      {!user && (
        <div style={{ display: "flex", gap: 8 }}>
          <Link className="btn btn-primary" to={`/signup?next=${next}`}>
            Create account
          </Link>
          <Link className="btn btn-secondary" to={`/login?next=${next}`}>
            Sign in
          </Link>
        </div>
      )}

      {user && (
        <>
          {acceptError && (
            <p role="alert" className="error-text">
              {acceptError}
            </p>
          )}
          <button
            className="btn btn-primary btn-block"
            onClick={accept}
            disabled={accepting || !canAccept}
            title={
              wrongAccount
                ? "Sign out and sign in with the invited email first"
                : unverified
                  ? "Confirm your email address first"
                  : undefined
            }
          >
            {accepting ? "Joining…" : "Accept invitation"}
          </button>
        </>
      )}
    </main>
  );
}
