import type { Role } from "@/types";

const LABELS: Record<Role, string> = {
  owner: "Owner",
  admin: "Admin",
  member: "Member",
  guest: "Guest",
};

export function RoleBadge({ role }: { role: Role }) {
  return <span className={`badge badge-${role}`}>{LABELS[role]}</span>;
}
