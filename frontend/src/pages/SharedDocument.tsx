import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { publicShareApi } from "@/api/publicShare";
import { ApiClientError, errorMessage } from "@/api/client";
import type { PublicShare } from "@/types";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// FR-11/12/15: what someone with a share link sees. No account, no workspace chrome: only the one
// document, and only what the link allows.
export function SharedDocumentPage() {
  const { token = "" } = useParams();
  const [share, setShare] = useState<PublicShare | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const open = useCallback(
    async (pw?: string) => {
      setBusy(true);
      try {
        setShare(await publicShareApi.open(token, pw));
        setPasswordError(null);
        setError(null);
      } catch (err) {
        // a wrong password stays on the form; anything else (gone, expired, locked out) replaces it
        if (pw !== undefined && err instanceof ApiClientError && err.code === "BAD_PASSWORD") {
          setPasswordError(err.message);
        } else {
          setShare(null);
          setError(errorMessage(err));
        }
      } finally {
        setBusy(false);
      }
    },
    [token],
  );

  useEffect(() => {
    void open();
  }, [open]);

  function submit(e: FormEvent) {
    e.preventDefault();
    void open(password);
  }

  const card = {
    maxWidth: 440,
    margin: "80px auto",
    padding: 24,
    background: "var(--color-bg-primary)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
  } as const;

  if (error) {
    return (
      <main style={card}>
        <h1 style={{ fontSize: 18, marginTop: 0 }}>This link can't be opened</h1>
        <p role="alert" style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
          {error}
        </p>
      </main>
    );
  }
  if (!share) {
    return (
      <main style={card}>
        <p style={{ fontSize: 13 }}>Loading…</p>
      </main>
    );
  }
  if (share.requires_password) {
    return (
      <main style={card}>
        <h1 style={{ fontSize: 18, marginTop: 0 }}>This document is password protected</h1>
        <form onSubmit={submit}>
          <div className="field">
            <input
              type="password"
              aria-label="Password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="off"
              autoFocus
            />
          </div>
          {passwordError && (
            <p className="error-text" role="alert">
              {passwordError}
            </p>
          )}
          <button className="btn btn-primary btn-block" disabled={busy || !password}>
            Open
          </button>
        </form>
      </main>
    );
  }
  return (
    <main style={card}>
      <h1 style={{ fontSize: 18, marginTop: 0, wordBreak: "break-word" }}>📄 {share.filename}</h1>
      <p style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
        {share.mime_type} · {formatSize(share.size_bytes ?? 0)}
        {share.expires_at
          ? ` · link expires ${new Date(share.expires_at).toLocaleDateString()}`
          : ""}
      </p>
      <div style={{ display: "flex", gap: 8 }}>
        {share.preview_url && (
          <a
            className="btn btn-secondary"
            href={share.preview_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            View
          </a>
        )}
        {share.download_url && (
          <a
            className="btn btn-primary"
            href={share.download_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Download
          </a>
        )}
      </div>
      {!share.download_url && !share.preview_url && (
        <p style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
          The owner has turned downloads off for this link, and this type of file can't be
          previewed.
        </p>
      )}
    </main>
  );
}
