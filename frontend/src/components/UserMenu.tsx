import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/auth/AuthContext";

// The signed-in user's profile: who they are, and Sign out. Signing out drops the session at once
// and revokes the token on the server, so a copied token stops working; ProtectedRoute then sends
// the user to the login page.
export function UserMenu({ placement = "down" }: { placement?: "up" | "down" }) {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;
  const initial = (user.name.trim()[0] ?? "?").toUpperCase();

  return (
    <div ref={root} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Profile menu"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          width: "100%",
          padding: "6px 8px",
          background: "var(--color-bg-primary)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-md)",
          fontSize: 12,
          textAlign: "left",
        }}
      >
        <span
          aria-hidden
          style={{
            width: 24,
            height: 24,
            flexShrink: 0,
            borderRadius: "50%",
            display: "grid",
            placeItems: "center",
            background: "var(--color-accent-soft)",
            color: "var(--color-accent)",
            fontWeight: 600,
          }}
        >
          {initial}
        </span>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {user.name}
        </span>
      </button>

      {open && (
        <div
          role="menu"
          style={{
            position: "absolute",
            [placement === "up" ? "bottom" : "top"]: "calc(100% + 6px)",
            left: 0,
            minWidth: 220,
            zIndex: 20,
            padding: 6,
            background: "var(--color-bg-primary)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
          }}
        >
          <div style={{ padding: "6px 8px 8px", fontSize: 12 }}>
            <div style={{ fontWeight: 600 }}>{user.name}</div>
            <div style={{ color: "var(--color-text-secondary)", wordBreak: "break-all" }}>
              {user.email}
            </div>
          </div>
          <button
            role="menuitem"
            className="btn btn-ghost"
            onClick={() => {
              setOpen(false);
              logout();
            }}
            style={{ width: "100%", justifyContent: "flex-start" }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
