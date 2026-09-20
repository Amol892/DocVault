import { useState, type FormEvent } from "react";
import { Modal } from "./Modal";
import { membersApi } from "@/api/members";
import type { InvitableRole } from "@/types";
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
  const [submitting, setSubmitting] = useState(false);
  const toast = useToast();
  const safe = useSafeAction();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    const res = await safe(() => membersApi.invite(workspaceId, email.trim(), role));
    setSubmitting(false);
    if (!res.ok) return; // the error is already shown; keep the form open so it can be corrected
    toast(`Invite sent to ${email}`);
    onInvited();
    onClose();
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
