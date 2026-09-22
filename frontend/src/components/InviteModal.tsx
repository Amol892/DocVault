import { useEffect, useState, type FormEvent } from "react";
import { Modal } from "./Modal";
import { membersApi } from "@/api/members";
import { documentsApi } from "@/api/documents";
import type { Document, InvitableRole, WorkspaceInvite } from "@/types";
import { useToast } from "@/hooks/useToast";
import { useSafeAction } from "@/hooks/useSafeAction";

interface InviteModalProps {
  workspaceId: string;
  workspaceName: string;
  onClose: () => void;
  onInvited: () => void;
}

export function InviteModal({ workspaceId, workspaceName, onClose, onInvited }: InviteModalProps) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InvitableRole>("member");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<WorkspaceInvite | null>(null);
  const toast = useToast();
  const safe = useSafeAction();

  // a Guest is invited to specific documents (FR-21), so offer the document list for that role
  useEffect(() => {
    if (role !== "guest" || documents.length > 0) return;
    let cancelled = false;
    safe(() => documentsApi.list({ workspace_id: workspaceId })).then((res) => {
      if (!cancelled && res.ok) setDocuments(res.value.items);
    });
    return () => {
      cancelled = true;
    };
  }, [role, documents.length, workspaceId, safe]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    const res = await safe(() =>
      membersApi.invite(workspaceId, email.trim(), role, role === "guest" ? documentIds : []),
    );
    setSubmitting(false);
    if (!res.ok) return; // the error is already shown; keep the form open so it can be corrected
    setResult(res.value);
    onInvited();
  }

  function copyLink() {
    if (!result?.url) return;
    navigator.clipboard?.writeText(result.url).then(
      () => toast("Link copied"),
      () => toast("Couldn't copy — select the link and copy it manually."),
    );
  }

  if (result) {
    return (
      <Modal title={`Invite to ${workspaceName}`} onClose={onClose}>
        <p style={{ fontSize: 13, marginTop: 0 }} role="status">
          {result.email_sent
            ? `An invitation was emailed to ${result.email}.`
            : `The email to ${result.email} could not be sent. Send them this link yourself.`}
        </p>
        {result.url && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "var(--color-bg-secondary)",
              borderRadius: "var(--radius-sm)",
              padding: "8px 10px",
            }}
          >
            <span
              style={{
                flex: 1,
                fontSize: 12,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {result.url}
            </span>
            <button className="btn btn-primary" style={{ padding: "4px 10px" }} onClick={copyLink}>
              Copy
            </button>
          </div>
        )}
        <p style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
          The link is shown only now, and only {result.email} can use it.
        </p>
        <button className="btn btn-secondary btn-block" onClick={onClose}>
          Done
        </button>
      </Modal>
    );
  }

  return (
    <Modal title={`Invite to ${workspaceName}`} onClose={onClose}>
      <form onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="invite-email">Email</label>
          <input
            id="invite-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="colleague@company.com"
          />
        </div>
        <div className="field">
          <label htmlFor="invite-role">Role</label>
          {/* Owner is intentionally not offered here — ownership only moves via
              explicit transfer (TRANSFER_OWNERSHIP), never via invite. */}
          <select
            id="invite-role"
            value={role}
            onChange={(e) => setRole(e.target.value as InvitableRole)}
          >
            <option value="admin">Admin</option>
            <option value="member">Member</option>
            <option value="guest">Guest</option>
          </select>
        </div>
        {role === "guest" && (
          <fieldset style={{ border: "none", padding: 0, margin: "0 0 8px" }}>
            <legend style={{ fontSize: 12, marginBottom: 4 }}>Documents they can see</legend>
            {documents.length === 0 && (
              <p style={{ fontSize: 12, color: "var(--color-text-secondary)", margin: 0 }}>
                No documents yet. You can grant access later from the Members page.
              </p>
            )}
            {documents.map((d) => (
              <label key={d.id} style={{ display: "block", fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={documentIds.includes(d.id)}
                  onChange={(e) =>
                    setDocumentIds((ids) =>
                      e.target.checked ? [...ids, d.id] : ids.filter((id) => id !== d.id),
                    )
                  }
                />{" "}
                {d.filename}
              </label>
            ))}
          </fieldset>
        )}
        <p style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
          If they don't have an account yet, they'll sign up first, then land in this workspace once
          they accept.
        </p>
        <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
          <button type="button" className="btn btn-secondary btn-block" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? "Sending…" : "Send invite"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
