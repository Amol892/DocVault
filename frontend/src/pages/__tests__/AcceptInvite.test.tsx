import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { AcceptInvitePage } from "../AcceptInvite";

const auth = vi.hoisted(() => ({
  user: null as { email: string; email_verified: boolean } | null,
  loading: false,
  logout: vi.fn(),
}));
const preview = vi.hoisted(() => vi.fn());
const acceptInvite = vi.hoisted(() => vi.fn());
const toast = vi.hoisted(() => vi.fn());
vi.mock("@/auth/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/api/invites", () => ({ invitesApi: { preview } }));
vi.mock("@/api/members", () => ({ membersApi: { acceptInvite } }));
vi.mock("@/hooks/useToast", () => ({ useToast: () => toast }));

const PREVIEW = { workspace_name: "Acme", role: "member", email: "ana@acme.com", expired: false };

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/invites/tok123"]}>
      <Routes>
        <Route path="/invites/:token" element={<AcceptInvitePage />} />
        <Route path="/workspaces" element={<p>workspaces page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AcceptInvitePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.user = null;
    auth.loading = false;
    preview.mockResolvedValue(PREVIEW);
  });

  it("sends a signed-out visitor to create an account or sign in, keeping the invitation", async () => {
    renderPage();
    expect(await screen.findByText(/Join Acme/)).toBeInTheDocument();
    expect(screen.getByText("ana@acme.com")).toBeInTheDocument();
    const next = encodeURIComponent("/invites/tok123");
    expect(screen.getByRole("link", { name: "Create account" })).toHaveAttribute(
      "href",
      `/signup?next=${next}`,
    );
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      `/login?next=${next}`,
    );
    expect(screen.queryByRole("button", { name: "Accept invitation" })).not.toBeInTheDocument();
  });

  it("lets the invited, verified person accept and go to their workspaces", async () => {
    auth.user = { email: "ANA@acme.com", email_verified: true };
    acceptInvite.mockResolvedValue(undefined);
    renderPage();
    const button = await screen.findByRole("button", { name: "Accept invitation" });
    expect(button).toBeEnabled();
    await userEvent.click(button);
    expect(acceptInvite).toHaveBeenCalledWith("tok123");
    expect(await screen.findByText("workspaces page")).toBeInTheDocument();
    expect(toast).toHaveBeenCalledWith("You joined Acme");
  });

  it("disables Accept and offers to sign out when signed in with a different email", async () => {
    auth.user = { email: "someone.else@acme.com", email_verified: true };
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/for ana@acme\.com/);
    expect(screen.getByRole("button", { name: "Accept invitation" })).toBeDisabled();
    // never even tries the doomed request
    expect(acceptInvite).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(auth.logout).toHaveBeenCalledTimes(1);
  });

  it("disables Accept and explains when the matching account isn't verified yet", async () => {
    auth.user = { email: "ana@acme.com", email_verified: false };
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/Confirm your email/);
    expect(screen.getByRole("button", { name: "Accept invitation" })).toBeDisabled();
    expect(acceptInvite).not.toHaveBeenCalled();
  });

  it("shows a failed accept inline, keeping the invite on screen (not a dead end)", async () => {
    auth.user = { email: "ana@acme.com", email_verified: true };
    acceptInvite.mockRejectedValue(
      new ApiClientError(
        403,
        "INVITE_EMAIL_MISMATCH",
        "This invitation was sent to a different email address.",
      ),
    );
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Accept invitation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("different email address");
    // the invite itself, and a retry, are still available — no forced navigation away
    expect(screen.getByText(/Join Acme/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept invitation" })).toBeInTheDocument();
  });

  it.each([
    [410, "INVITE_EXPIRED", "This invitation has expired."],
    [410, "INVITE_REVOKED", "This invitation was revoked."],
    [404, "NOT_FOUND", "This invitation doesn't exist."],
  ])("explains a %s %s invitation", async (status, code, message) => {
    preview.mockRejectedValue(new ApiClientError(status, code, message));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });
});
