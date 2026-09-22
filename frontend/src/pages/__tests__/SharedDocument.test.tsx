import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import type { PublicShare } from "@/types";
import { SharedDocumentPage } from "../SharedDocument";

const open = vi.hoisted(() => vi.fn());
vi.mock("@/api/publicShare", () => ({ publicShareApi: { open } }));

const SHARE: PublicShare = {
  requires_password: false,
  filename: "plan.pdf",
  mime_type: "application/pdf",
  size_bytes: 2048,
  allow_download: true,
  expires_at: null,
  download_url: "https://storage.example/dl",
  preview_url: "https://storage.example/view",
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/s/tok123"]}>
      <Routes>
        <Route path="/s/:token" element={<SharedDocumentPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SharedDocumentPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("opens the link without a password and offers view and download", async () => {
    open.mockResolvedValue(SHARE);
    renderPage();
    expect(await screen.findByText(/plan\.pdf/)).toBeInTheDocument();
    expect(open).toHaveBeenCalledWith("tok123", undefined);
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute(
      "href",
      "https://storage.example/dl",
    );
    expect(screen.getByRole("link", { name: "View" })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
  });

  it("offers no download when the owner turned it off", async () => {
    open.mockResolvedValue({ ...SHARE, allow_download: false, download_url: null });
    renderPage();
    await screen.findByText(/plan\.pdf/);
    expect(screen.queryByRole("link", { name: "Download" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View" })).toBeInTheDocument();
  });

  it("asks for the password, keeps the form on a wrong one, and opens on the right one", async () => {
    open.mockResolvedValueOnce({ ...SHARE, requires_password: true, filename: null });
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Password"), "nope");
    open.mockRejectedValueOnce(new ApiClientError(403, "BAD_PASSWORD", "That password is wrong."));
    await user.click(screen.getByRole("button", { name: "Open" }));
    expect(await screen.findByText("That password is wrong.")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();

    open.mockResolvedValueOnce(SHARE);
    await user.clear(screen.getByLabelText("Password"));
    await user.type(screen.getByLabelText("Password"), "open-sesame");
    await user.click(screen.getByRole("button", { name: "Open" }));
    expect(await screen.findByText(/plan\.pdf/)).toBeInTheDocument();
    expect(open).toHaveBeenLastCalledWith("tok123", "open-sesame");
  });

  it.each([
    ["LINK_REVOKED", 410, "This link has been revoked."],
    ["LINK_EXPIRED", 410, "This link has expired."],
    ["NOT_FOUND", 404, "This link doesn't exist."],
  ])("explains a %s link", async (code, status, message) => {
    open.mockRejectedValue(new ApiClientError(status, code, message));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByRole("link", { name: "Download" })).not.toBeInTheDocument();
  });
});
