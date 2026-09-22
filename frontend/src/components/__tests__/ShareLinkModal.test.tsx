import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Document, ShareLink } from "@/types";
import { ShareLinkModal } from "../ShareLinkModal";

const shareLinksApi = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  revoke: vi.fn(),
  accessLog: vi.fn(),
  updateAllowDownload: vi.fn(),
}));
vi.mock("@/api/shareLinks", () => ({ shareLinksApi }));

const DOC = { id: "d1", filename: "plan.pdf" } as Document;

const ACTIVE: ShareLink = {
  id: "l1",
  document_id: "d1",
  allow_download: true,
  has_password: false,
  expires_at: null,
  expired: false,
  revoked_at: null,
  created_at: "2026-09-01T00:00:00Z",
};

function open(onVisibilityChanged = vi.fn()) {
  render(
    <ShareLinkModal document={DOC} onClose={vi.fn()} onVisibilityChanged={onVisibilityChanged} />,
  );
  return onVisibilityChanged;
}

describe("ShareLinkModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    shareLinksApi.accessLog.mockResolvedValue({ items: [], page: 1, total: 0 });
  });

  it("does not pretend it can show the address of an existing link (only a hash is stored)", async () => {
    shareLinksApi.list.mockResolvedValue([ACTIVE]);
    open();
    expect(await screen.findByText(/only shown when it is created/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Revoke link" })).toBeInTheDocument();
  });

  it("shows the address, with Copy, right after a link is created", async () => {
    shareLinksApi.list.mockResolvedValue([]);
    shareLinksApi.create.mockResolvedValue({ ...ACTIVE, url: "https://vault.example/s/abc123" });
    const changed = open();

    await userEvent.setup().click(await screen.findByRole("button", { name: "Generate link" }));

    expect(await screen.findByText("https://vault.example/s/abc123")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
    expect(changed).toHaveBeenCalledWith("d1", "public");
  });

  it("sends the chosen options, with a password only when one is required", async () => {
    shareLinksApi.list.mockResolvedValue([]);
    shareLinksApi.create.mockResolvedValue({ ...ACTIVE, url: "https://vault.example/s/x" });
    open();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("switch", { name: "Allow download" })); // turn off
    await user.click(screen.getByRole("switch", { name: "Require password" }));
    await user.type(screen.getByLabelText("Link password"), "s3cret");
    await user.click(screen.getByRole("button", { name: "Generate link" }));

    expect(shareLinksApi.create).toHaveBeenCalledWith(
      "d1",
      expect.objectContaining({ allow_download: false, password: "s3cret" }),
    );
  });

  it("does not create a link with an empty password when one is required", async () => {
    shareLinksApi.list.mockResolvedValue([]);
    open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("switch", { name: "Require password" }));
    await user.click(screen.getByRole("button", { name: "Generate link" }));
    expect(shareLinksApi.create).not.toHaveBeenCalled();
  });

  it("keeps the link and does not report success when revoking fails", async () => {
    shareLinksApi.list.mockResolvedValue([ACTIVE]);
    shareLinksApi.revoke.mockRejectedValue(new Error("network down"));
    const changed = open();

    await userEvent.setup().click(await screen.findByRole("button", { name: "Revoke link" }));

    expect(changed).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Revoke link" })).toBeInTheDocument();
  });

  it("treats an expired link as no active link, so a new one can be generated", async () => {
    shareLinksApi.list.mockResolvedValue([{ ...ACTIVE, expired: true }]);
    open();
    expect(await screen.findByRole("button", { name: "Generate link" })).toBeInTheDocument();
  });

  it("shows who recently opened the active link", async () => {
    shareLinksApi.list.mockResolvedValue([ACTIVE]);
    shareLinksApi.accessLog.mockResolvedValue({
      items: [
        {
          accessed_at: "2026-09-21T10:00:00Z",
          ip_address: "203.0.113.7",
          user_agent: "x",
          outcome: "bad_password",
        },
      ],
      page: 1,
      total: 1,
    });
    open();
    expect(await screen.findByText(/203\.0\.113\.7/)).toBeInTheDocument();
    expect(screen.getByText("bad password")).toBeInTheDocument();
  });

  it("toggles allow-download on an existing link without recreating it", async () => {
    shareLinksApi.list.mockResolvedValue([ACTIVE]);
    shareLinksApi.updateAllowDownload.mockResolvedValue({ ...ACTIVE, allow_download: false });
    open();
    const toggle = await screen.findByRole("switch", { name: "Allow download" });
    expect(toggle).toBeEnabled();
    expect(toggle).toHaveAttribute("aria-checked", "true");

    await userEvent.click(toggle);

    expect(shareLinksApi.updateAllowDownload).toHaveBeenCalledWith("l1", false);
    expect(shareLinksApi.create).not.toHaveBeenCalled();
    await vi.waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "false"));
  });

  it("the other options stay locked once a link exists", async () => {
    shareLinksApi.list.mockResolvedValue([ACTIVE]);
    open();
    await screen.findByRole("switch", { name: "Allow download" });
    expect(screen.getByRole("switch", { name: "Require password" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "Set expiry (30 days)" })).toBeDisabled();
  });
});
