import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Document } from "@/types";
import { TrashPage } from "../Trash";

const state = vi.hoisted(() => ({ myRole: "member" as string, toast: vi.fn() }));
const docs = vi.hoisted(() => ({ trash: vi.fn(), restore: vi.fn() }));

vi.mock("@/workspace/WorkspaceContext", () => ({ useWorkspace: () => ({ myRole: state.myRole }) }));
vi.mock("@/components/Sidebar", () => ({ Sidebar: () => null }));
vi.mock("@/hooks/useToast", () => ({ useToast: () => state.toast }));
vi.mock("@/api/documents", () => ({ documentsApi: docs }));

const DOC = {
  id: "d1",
  filename: "old.pdf",
  deleted_at: "2026-09-20T10:00:00Z",
} as Document;

function renderPage() {
  return render(
    <MemoryRouter>
      <TrashPage />
    </MemoryRouter>,
  );
}

describe("TrashPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.myRole = "member";
  });

  it("lists deleted documents and restores one", async () => {
    docs.trash.mockResolvedValueOnce({ items: [DOC], page: 1, total: 1 });
    docs.restore.mockResolvedValue({ ...DOC, deleted_at: null });
    docs.trash.mockResolvedValueOnce({ items: [], page: 1, total: 0 });
    renderPage();
    expect(await screen.findByText(/old\.pdf/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Restore" }));
    expect(docs.restore).toHaveBeenCalledWith("d1");
    expect(await screen.findByText("The trash is empty.")).toBeInTheDocument();
    expect(state.toast).toHaveBeenCalledWith(expect.stringContaining("restored"));
  });

  it("shows an empty state", async () => {
    docs.trash.mockResolvedValue({ items: [], page: 1, total: 0 });
    renderPage();
    expect(await screen.findByText("The trash is empty.")).toBeInTheDocument();
  });

  it("does not ask the server for guests", async () => {
    state.myRole = "guest";
    renderPage();
    expect(screen.getByText(/isn't available to Guests/)).toBeInTheDocument();
    await waitFor(() => expect(docs.trash).not.toHaveBeenCalled());
  });
});
