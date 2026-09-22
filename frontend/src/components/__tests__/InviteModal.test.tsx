import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Document, WorkspaceInvite } from "@/types";
import { InviteModal } from "../InviteModal";

const membersApi = vi.hoisted(() => ({ invite: vi.fn() }));
const documentsApi = vi.hoisted(() => ({ list: vi.fn() }));
const toast = vi.hoisted(() => vi.fn());
vi.mock("@/api/members", () => ({ membersApi }));
vi.mock("@/api/documents", () => ({ documentsApi }));
vi.mock("@/hooks/useToast", () => ({ useToast: () => toast }));

const CREATED: WorkspaceInvite = {
  id: "i1",
  email: "new@x.com",
  role: "member",
  expires_at: "2026-10-01T00:00:00Z",
  created_at: "2026-09-21T00:00:00Z",
  expired: false,
  url: "https://vault.example/invites/tok",
  email_sent: true,
};

const DOC = (over: Partial<Document>): Document => ({
  id: "d1",
  owner_id: "u1",
  owner_name: "Ada",
  workspace_id: "w1",
  folder_id: null,
  filename: "report.pdf",
  mime_type: "application/pdf",
  size_bytes: 10,
  visibility: "workspace",
  deleted_at: null,
  created_at: "",
  updated_at: "",
  ...over,
});

function open() {
  const onInvited = vi.fn();
  render(
    <InviteModal workspaceId="w1" workspaceName="Acme" onClose={vi.fn()} onInvited={onInvited} />,
  );
  return onInvited;
}

describe("InviteModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    documentsApi.list.mockResolvedValue({
      items: [DOC({ id: "d1", filename: "Legal.pdf" }), DOC({ id: "d2", filename: "2026.pdf" })],
      page: 1,
      total: 2,
    });
  });

  it("sends the invite and then shows the emailed confirmation with a copyable link", async () => {
    membersApi.invite.mockResolvedValue(CREATED);
    const onInvited = open();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), " new@x.com ");
    await user.click(screen.getByRole("button", { name: "Send invite" }));

    expect(membersApi.invite).toHaveBeenCalledWith("w1", "new@x.com", "member", []);
    expect(await screen.findByText(/emailed to new@x\.com/)).toBeInTheDocument();
    expect(screen.getByText("https://vault.example/invites/tok")).toBeInTheDocument();
    expect(onInvited).toHaveBeenCalled();
  });

  it("tells the admin to hand the link over when the email could not be sent", async () => {
    membersApi.invite.mockResolvedValue({ ...CREATED, email_sent: false });
    open();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "new@x.com");
    await user.click(screen.getByRole("button", { name: "Send invite" }));
    expect(await screen.findByText(/could not be sent/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
  });

  it("offers documents only for a Guest and sends the chosen ones", async () => {
    membersApi.invite.mockResolvedValue({ ...CREATED, role: "guest" });
    open();
    const user = userEvent.setup();
    expect(screen.queryByText("Documents they can see")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Email"), "g@x.com");
    await user.selectOptions(screen.getByLabelText("Role"), "guest");
    await user.click(await screen.findByLabelText("2026.pdf"));
    await user.click(screen.getByRole("button", { name: "Send invite" }));
    expect(membersApi.invite).toHaveBeenCalledWith("w1", "g@x.com", "guest", ["d2"]);
  });

  it("does not send documents for a non-guest role, even if some were ticked earlier", async () => {
    membersApi.invite.mockResolvedValue(CREATED);
    open();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "m@x.com");
    await user.selectOptions(screen.getByLabelText("Role"), "guest");
    await user.click(await screen.findByLabelText("Legal.pdf"));
    await user.selectOptions(screen.getByLabelText("Role"), "admin");
    await user.click(screen.getByRole("button", { name: "Send invite" }));
    expect(membersApi.invite).toHaveBeenCalledWith("w1", "m@x.com", "admin", []);
  });

  it("stays on the form when the server refuses", async () => {
    membersApi.invite.mockRejectedValue(new Error("This person is already a member."));
    const onInvited = open();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "dup@x.com");
    await user.click(screen.getByRole("button", { name: "Send invite" }));
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith("This person is already a member."));
    expect(screen.getByRole("button", { name: "Send invite" })).toBeInTheDocument();
    expect(onInvited).not.toHaveBeenCalled();
  });
});
