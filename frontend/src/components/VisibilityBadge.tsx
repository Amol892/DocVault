import type { DocumentVisibility } from "@/types";

const LABELS: Record<DocumentVisibility, string> = {
  private: "🔒 Private",
  workspace: "👥 Workspace",
  public: "🔗 Public link",
};

// FR-27/FR-29 (spec §7.6/§6): every document's visibility must be legible at a
// glance — this badge is the one place that rule is implemented, reused
// everywhere a document row is rendered so it can never drift between views.
export function VisibilityBadge({ visibility }: { visibility: DocumentVisibility }) {
  return <span className={`badge badge-${visibility}`}>{LABELS[visibility]}</span>;
}
