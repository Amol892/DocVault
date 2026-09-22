import { useEffect, useState } from "react";
import { Modal } from "./Modal";
import { shareLinksApi } from "@/api/shareLinks";
import { useToast } from "@/hooks/useToast";
import { useSafeAction } from "@/hooks/useSafeAction";
import type { Document, ShareAccessLogEntry, ShareLink } from "@/types";

interface ShareLinkModalProps {
  document: Document;
  onClose: () => void;
  onVisibilityChanged: (docId: string, visibility: "workspace" | "public") => void;
}

// FR-10..15: allow-download / password / expiry are set at link-creation time.
// Revoking sets revoked_at server-side and is checked on every future access —
// this modal never assumes revocation succeeded without the API confirming it.
//
// The server stores only a hash of the link token, so the URL exists in exactly one place: the
// response that creates the link. It is shown (and can be copied) right then; when the modal is
// opened again for an existing link there is no URL to show.
export function ShareLinkModal({ document, onClose, onVisibilityChanged }: ShareLinkModalProps) {
  const [link, setLink] = useState<ShareLink | null>(null);
  const [loading, setLoading] = useState(true);
  const [allowDownload, setAllowDownload] = useState(true);
  const [requirePassword, setRequirePassword] = useState(false);
  const [password, setPassword] = useState("");
  const [setExpiry, setSetExpiry] = useState(true);
  const [log, setLog] = useState<ShareAccessLogEntry[]>([]);
  const toast = useToast();
  const safe = useSafeAction();

  // FR-14: recent openings of the active link
  const linkId = link?.id;
  useEffect(() => {
    if (!linkId) {
      setLog([]);
      return;
    }
    let cancelled = false;
    safe(() => shareLinksApi.accessLog(linkId)).then((res) => {
      if (!cancelled && res.ok) setLog(res.value.items.slice(0, 5));
    });
    return () => {
      cancelled = true;
    };
  }, [linkId, safe]);

  useEffect(() => {
    let cancelled = false;
    safe(() => shareLinksApi.list(document.id)).then((res) => {
      if (cancelled) return;
      if (res.ok) setLink(res.value.find((l) => !l.revoked_at && !l.expired) ?? null);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [document.id, safe]);

  async function generateLink() {
    if (requirePassword && !password) {
      toast('Enter a password, or turn off "Require password".');
      return;
    }
    const expires_at = setExpiry
      ? new Date(Date.now() + 30 * 24 * 3600 * 1000).toISOString()
      : null;
    const res = await safe(() =>
      shareLinksApi.create(document.id, {
        allow_download: allowDownload,
        password: requirePassword ? password : null,
        expires_at,
      }),
    );
    if (!res.ok) return;
    setLink(res.value);
    setPassword("");
    onVisibilityChanged(document.id, "public");
    toast("Public share link created");
  }

  async function toggleDownload(checked: boolean) {
    if (!link) {
      setAllowDownload(checked);
      return;
    }
    const res = await safe(() => shareLinksApi.updateAllowDownload(link.id, checked));
    if (res.ok) setLink(res.value);
  }

  async function revokeLink() {
    if (!link) return;
    const res = await safe(() => shareLinksApi.revoke(link.id));
    if (!res.ok) return;
    setLink(null);
    onVisibilityChanged(document.id, "workspace");
    toast("Link revoked — no longer accessible to anyone outside the workspace");
    onClose();
  }

  function copyLink() {
    if (!link?.url) return;
    navigator.clipboard?.writeText(link.url).then(
      () => toast("Link copied"),
      () => toast("Couldn't copy — select the link and copy it manually."),
    );
  }

  if (loading) return null;

  return (
    <Modal title={`Share "${document.filename}"`} onClose={onClose}>
      {link?.url && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            background: "var(--color-bg-secondary)",
            borderRadius: "var(--radius-sm)",
            padding: "8px 10px",
            marginBottom: 16,
          }}
        >
          <span
            style={{
              flex: 1,
              fontSize: 12,
              color: "var(--color-text-secondary)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {link.url}
          </span>
          <button className="btn btn-primary" style={{ padding: "4px 10px" }} onClick={copyLink}>
            Copy
          </button>
        </div>
      )}
      {link && !link.url && (
        <p style={{ fontSize: 13, color: "var(--color-text-secondary)", marginTop: 0 }}>
          This link is active. For security its address is only shown when it is created. Revoke it
          and generate a new one if you need the address again.
        </p>
      )}
      {!link && (
        <p style={{ fontSize: 13, color: "var(--color-text-secondary)", marginTop: 0 }}>
          No active link yet — set the options below and generate one.
        </p>
      )}

      <ToggleRow
        label="Allow download"
        sub="Recipients can download, not just view — changeable any time, even after the link is out"
        checked={link ? link.allow_download : allowDownload}
        onChange={toggleDownload}
      />
      <ToggleRow
        label="Require password"
        sub="Adds a password prompt before access"
        checked={link ? link.has_password : requirePassword}
        onChange={setRequirePassword}
        disabled={!!link}
      />
      {requirePassword && !link && (
        <div className="field" style={{ marginTop: 8 }}>
          <input
            type="password"
            aria-label="Link password"
            placeholder="Link password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
        </div>
      )}
      <ToggleRow
        label="Set expiry (30 days)"
        sub="Link stops working after that date"
        checked={link ? link.expires_at !== null : setExpiry}
        onChange={setSetExpiry}
        disabled={!!link}
      />

      {link && (
        <div style={{ marginTop: 16, fontSize: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Recent access</div>
          {log.length === 0 && (
            <div style={{ color: "var(--color-text-secondary)" }}>Nobody has opened it yet.</div>
          )}
          {log.map((entry, i) => (
            <div
              key={i}
              style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}
            >
              <span>
                {new Date(entry.accessed_at).toLocaleString()} · {entry.ip_address ?? "unknown"}
              </span>
              <span style={{ color: "var(--color-text-secondary)" }}>
                {entry.outcome === "ok" ? "opened" : entry.outcome.replace("_", " ")}
              </span>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
        {link ? (
          <button className="btn btn-danger btn-block" onClick={revokeLink}>
            Revoke link
          </button>
        ) : (
          <button className="btn btn-primary btn-block" onClick={generateLink}>
            Generate link
          </button>
        )}
        <button className="btn btn-secondary btn-block" onClick={onClose}>
          Close
        </button>
      </div>
    </Modal>
  );
}

function ToggleRow({
  label,
  sub,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  sub: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px 0",
        borderTop: "1px solid var(--color-border)",
        gap: 12,
      }}
    >
      <div>
        <div style={{ fontSize: 13, fontWeight: 500 }}>{label}</div>
        <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginTop: 1 }}>
          {sub}
        </div>
      </div>
      <button
        role="switch"
        aria-label={label}
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        style={{
          width: 36,
          height: 20,
          borderRadius: 999,
          position: "relative",
          border: "none",
          background: checked ? "var(--color-accent)" : "var(--color-border)",
          flexShrink: 0,
          opacity: disabled ? 0.6 : 1,
          cursor: disabled ? "not-allowed" : "pointer",
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 2,
            left: checked ? 18 : 2,
            width: 16,
            height: 16,
            borderRadius: 999,
            background: "#fff",
          }}
        />
      </button>
    </div>
  );
}
