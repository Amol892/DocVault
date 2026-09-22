import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Document } from "@/types";
import { DashboardPage } from "../Dashboard";

const state = vi.hoisted(() => ({ myRole: "member" as string, toast: vi.fn() }));
const docs = vi.hoisted(() => ({
  list: vi.fn(),
  rename: vi.fn(),
  move: vi.fn(),
  softDelete: vi.fn(),
  upload: vi.fn(),
  versions: vi.fn(),
  getVersionDownloadUrl: vi.fn(),
  getDownloadUrl: vi.fn(),
  getPreviewUrl: vi.fn(),
}));
const folders = vi.hoisted(() => ({ list: vi.fn() }));

vi.mock("@/workspace/WorkspaceContext", () => ({ useWorkspace: () => ({ myRole: state.myRole }) }));
vi.mock("@/components/Sidebar", () => ({ Sidebar: () => null }));
vi.mock("@/hooks/useToast", () => ({ useToast: () => state.toast }));
vi.mock("@/api/documents", () => ({ documentsApi: docs }));
vi.mock("@/api/folders", () => ({ foldersApi: folders }));

const DOC: Document = {
  id: "d1",
  owner_id: "u1",
  owner_name: "Ada",
  workspace_id: "w1",
  folder_id: null,
  filename: "plan.pdf",
  mime_type: "application/pdf",
  size_bytes: 10,
  visibility: "workspace",
  deleted_at: null,
  created_at: "2026-09-21T10:00:00Z",
  updated_at: "2026-09-21T10:00:00Z",
};

function renderPage() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  );
}

describe("Dashboard document actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
    state.myRole = "member";
    docs.list.mockResolvedValue({ items: [DOC], page: 1, total: 1 });
    folders.list.mockResolvedValue([
      { id: "f1", workspace_id: "w1", parent_folder_id: null, name: "Legal" },
    ]);
  });

  it("a member can rename a document and the list reloads", async () => {
    renderPage();
    await screen.findByText(/plan\.pdf/);
    vi.spyOn(window, "prompt").mockReturnValue("final.pdf");
    docs.rename.mockResolvedValue({ ...DOC, filename: "final.pdf" });
    await userEvent.click(screen.getByRole("button", { name: "Rename" }));
    expect(docs.rename).toHaveBeenCalledWith("d1", "final.pdf");
    await waitFor(() => expect(docs.list).toHaveBeenCalledTimes(2));
  });

  it("deletes only after confirmation", async () => {
    renderPage();
    await screen.findByText(/plan\.pdf/);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(docs.softDelete).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    docs.softDelete.mockResolvedValue(undefined);
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(docs.softDelete).toHaveBeenCalledWith("d1");
    await waitFor(() => expect(state.toast).toHaveBeenCalledWith(expect.stringContaining("trash")));
  });

  it("moves a document to a chosen folder", async () => {
    renderPage();
    await screen.findByText(/plan\.pdf/);
    docs.move.mockResolvedValue({ ...DOC, folder_id: "f1" });
    await userEvent.click(screen.getByRole("button", { name: "Move" }));
    await userEvent.selectOptions(await screen.findByLabelText("Destination folder"), "f1");
    await userEvent.click(screen.getByRole("button", { name: "Move here" }));
    expect(docs.move).toHaveBeenCalledWith("d1", "f1");
  });

  it("shows the version history and downloads an old version", async () => {
    renderPage();
    await screen.findByText(/plan\.pdf/);
    docs.versions.mockResolvedValue([
      {
        version_number: 2,
        size_bytes: 2048,
        mime_type: "application/pdf",
        created_by_name: "Ada",
        created_at: "2026-09-21T11:00:00Z",
        is_current: true,
      },
      {
        version_number: 1,
        size_bytes: 10,
        mime_type: "application/pdf",
        created_by_name: "Ada",
        created_at: "2026-09-21T10:00:00Z",
        is_current: false,
      },
    ]);
    docs.getVersionDownloadUrl.mockResolvedValue("https://storage.example/v1");
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    await userEvent.click(screen.getByRole("button", { name: "Versions" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Version 2/)).toBeInTheDocument();
    expect(within(dialog).getByText(/\(current\)/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Download version 1" }));
    expect(docs.getVersionDownloadUrl).toHaveBeenCalledWith("d1", 1);
    expect(open).toHaveBeenCalledWith("https://storage.example/v1", "_blank", "noopener");
  });

  it("uploads a new version of an existing document", async () => {
    renderPage();
    await screen.findByText(/plan\.pdf/);
    docs.upload.mockResolvedValue(DOC);
    await userEvent.click(screen.getByRole("button", { name: "New version" }));
    const file = new File(["%PDF-1.7"], "plan.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByLabelText("Choose the new version"), file);
    expect(docs.upload).toHaveBeenCalledWith(file, { documentId: "d1" });
  });

  it("a guest can view versions and download but has no write actions", async () => {
    state.myRole = "guest";
    renderPage();
    await screen.findByText(/plan\.pdf/);
    expect(screen.getByRole("button", { name: "Versions" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download" })).toBeInTheDocument();
    for (const name of ["Rename", "Move", "New version", "Delete"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });

  it("opens the preview by clicking the filename itself, for a previewable document", async () => {
    renderPage();
    await screen.findByText(/plan\.pdf/);
    docs.getPreviewUrl.mockResolvedValue("https://storage.example/inline");
    await userEvent.click(screen.getByRole("button", { name: "Preview plan.pdf" }));
    const dialog = await screen.findByRole("dialog");
    expect(docs.getPreviewUrl).toHaveBeenCalledWith("d1");
    expect(within(dialog).getByTitle("plan.pdf")).toHaveAttribute(
      "src",
      "https://storage.example/inline",
    );
  });

  it("the filename is plain text, not clickable, for a type that can't be previewed", async () => {
    docs.list.mockResolvedValue({
      items: [{ ...DOC, id: "d2", filename: "archive.zip", mime_type: "application/zip" }],
      page: 1,
      total: 1,
    });
    renderPage();
    await screen.findByText(/archive\.zip/);
    expect(screen.queryByRole("button", { name: /archive\.zip/ })).not.toBeInTheDocument();
  });

  it("offers View for a previewable document and opens it inline", async () => {
    renderPage();
    await screen.findByText(/plan\.pdf/);
    docs.getPreviewUrl.mockResolvedValue("https://storage.example/inline");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    const dialog = await screen.findByRole("dialog");
    expect(docs.getPreviewUrl).toHaveBeenCalledWith("d1");
    expect(within(dialog).getByTitle("plan.pdf")).toHaveAttribute(
      "src",
      "https://storage.example/inline",
    );
  });

  it("offers no View button for a type that can't be previewed", async () => {
    docs.list.mockResolvedValue({
      items: [{ ...DOC, id: "d2", filename: "archive.zip", mime_type: "application/zip" }],
      page: 1,
      total: 1,
    });
    renderPage();
    await screen.findByText(/archive\.zip/);
    expect(screen.queryByRole("button", { name: "View" })).not.toBeInTheDocument();
  });

  it("a guest can also view a previewable document", async () => {
    state.myRole = "guest";
    renderPage();
    await screen.findByText(/plan\.pdf/);
    expect(screen.getByRole("button", { name: "View" })).toBeInTheDocument();
  });
});
