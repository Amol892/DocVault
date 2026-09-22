import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Folder, Role } from "@/types";
import { Sidebar } from "../Sidebar";

const FOLDERS: Folder[] = [
  { id: "f1", workspace_id: "w1", parent_folder_id: null, name: "Contracts" },
  { id: "f2", workspace_id: "w1", parent_folder_id: null, name: "Design" },
];

const state = vi.hoisted(() => ({ myRole: "member" as string, toast: vi.fn(), logout: vi.fn() }));

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "u1", name: "Ada", email: "ada@example.com" },
    logout: state.logout,
  }),
}));

vi.mock("@/workspace/WorkspaceContext", () => ({
  useWorkspace: () => ({ workspace: { id: "w1", name: "Acme" }, myRole: state.myRole }),
}));
const mockNavigate = vi.hoisted(() => vi.fn());
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => mockNavigate,
}));
vi.mock("@/hooks/useToast", () => ({ useToast: () => state.toast }));
vi.mock("@/api/folders", () => ({
  foldersApi: {
    list: vi.fn(),
    create: vi.fn(),
    rename: vi.fn(),
    delete: vi.fn(),
    move: vi.fn(),
  },
}));

import { ApiClientError } from "@/api/client";
import { foldersApi } from "@/api/folders";

function setup(role: Role, folders: Folder[] = FOLDERS) {
  state.myRole = role;
  vi.mocked(foldersApi.list).mockResolvedValue(folders);
  return render(
    <MemoryRouter>
      <Sidebar workspaceId="w1" />
    </MemoryRouter>,
  );
}

describe("Sidebar folder list", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("shows exactly the folders the API returned, with no client-side filtering", async () => {
    // the server already scoped a guest's list; the UI must not hide or add anything
    setup("guest", [FOLDERS[1]]);
    expect(await screen.findByText("📁 Design")).toBeInTheDocument();
    expect(screen.queryByText("📁 Contracts")).not.toBeInTheDocument();
  });

  it("a guest gets no folder controls and no Members link", async () => {
    setup("guest");
    await screen.findByText("📁 Design");
    expect(screen.queryByText("+ New folder")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Rename Design")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Delete Design")).not.toBeInTheDocument();
    expect(screen.queryByText("👥 Members & Roles")).not.toBeInTheDocument();
  });

  it("a member gets folder controls and the Members link", async () => {
    setup("member");
    await screen.findByText("📁 Design");
    expect(screen.getByText("+ New folder")).toBeInTheDocument();
    expect(screen.getByLabelText("Rename Design")).toBeInTheDocument();
    expect(screen.getByLabelText("Delete Design")).toBeInTheDocument();
    expect(screen.getByText("👥 Members & Roles")).toBeInTheDocument();
  });
});

describe("Sidebar folder actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("creates a folder and refreshes the list", async () => {
    setup("member");
    await screen.findByText("📁 Design");
    vi.spyOn(window, "prompt").mockReturnValue("  Legal ");
    vi.mocked(foldersApi.create).mockResolvedValue({
      id: "f3",
      workspace_id: "w1",
      parent_folder_id: null,
      name: "Legal",
    });
    vi.mocked(foldersApi.list).mockResolvedValue([
      ...FOLDERS,
      { id: "f3", workspace_id: "w1", parent_folder_id: null, name: "Legal" },
    ]);

    await userEvent.click(screen.getByText("+ New folder"));

    expect(foldersApi.create).toHaveBeenCalledWith("w1", "Legal", null);
    expect(await screen.findByText("📁 Legal")).toBeInTheDocument();
  });

  it("does nothing when the prompt is cancelled or left empty", async () => {
    setup("member");
    await screen.findByText("📁 Design");
    const prompt = vi.spyOn(window, "prompt");
    prompt.mockReturnValueOnce(null).mockReturnValueOnce("   ");
    await userEvent.click(screen.getByText("+ New folder"));
    await userEvent.click(screen.getByText("+ New folder"));
    expect(foldersApi.create).not.toHaveBeenCalled();
  });

  it("shows the server's message as a toast when the name is taken", async () => {
    setup("member");
    await screen.findByText("📁 Design");
    vi.spyOn(window, "prompt").mockReturnValue("Design");
    vi.mocked(foldersApi.create).mockRejectedValue(
      new ApiClientError(409, "NAME_TAKEN", "A folder with this name already exists here."),
    );

    await userEvent.click(screen.getByText("+ New folder"));

    await waitFor(() =>
      expect(state.toast).toHaveBeenCalledWith("A folder with this name already exists here."),
    );
  });

  it("renames a folder", async () => {
    setup("member");
    await screen.findByText("📁 Design");
    vi.spyOn(window, "prompt").mockReturnValue("Brand");
    vi.mocked(foldersApi.rename).mockResolvedValue({ ...FOLDERS[1], name: "Brand" });
    vi.mocked(foldersApi.list).mockResolvedValue([FOLDERS[0], { ...FOLDERS[1], name: "Brand" }]);

    await userEvent.click(screen.getByLabelText("Rename Design"));

    expect(foldersApi.rename).toHaveBeenCalledWith("f2", "Brand");
    expect(await screen.findByText("📁 Brand")).toBeInTheDocument();
  });

  it("deletes a folder only after confirmation", async () => {
    setup("member");
    await screen.findByText("📁 Design");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await userEvent.click(screen.getByLabelText("Delete Design"));
    expect(foldersApi.delete).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    vi.mocked(foldersApi.delete).mockResolvedValue(undefined);
    vi.mocked(foldersApi.list).mockResolvedValue([FOLDERS[0]]);
    await userEvent.click(screen.getByLabelText("Delete Design"));

    expect(foldersApi.delete).toHaveBeenCalledWith("f2");
    await waitFor(() => expect(screen.queryByText("📁 Design")).not.toBeInTheDocument());
  });
});

describe("Sidebar workspace header", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("shows the workspace name as a label and a separate button back to all workspaces", async () => {
    setup("member");
    await screen.findByText("📄 All Documents");
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Acme/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /All workspaces/ }));
    expect(mockNavigate).toHaveBeenCalledWith("/workspaces");
  });
});

describe("Sidebar profile menu", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it.each(["guest", "member", "owner"] as const)(
    "%s sees their profile and can sign out",
    async (role) => {
      setup(role);
      await screen.findByText("📄 All Documents");
      expect(screen.queryByRole("menu")).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Profile menu" }));
      expect(screen.getByText("ada@example.com")).toBeInTheDocument();
      await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
      expect(state.logout).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    },
  );

  it("closes the menu on Escape without signing out", async () => {
    setup("member");
    await screen.findByText("📄 All Documents");
    await userEvent.click(screen.getByRole("button", { name: "Profile menu" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(state.logout).not.toHaveBeenCalled();
  });
});

describe("Sidebar nested folders and trash", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("creates a subfolder inside the chosen folder", async () => {
    setup("member");
    await screen.findByText("📁 Design");
    vi.spyOn(window, "prompt").mockReturnValue("Icons");
    vi.mocked(foldersApi.create).mockResolvedValue({
      id: "f9",
      workspace_id: "w1",
      parent_folder_id: "f2",
      name: "Icons",
    });
    await userEvent.click(screen.getByLabelText("New folder in Design"));
    expect(foldersApi.create).toHaveBeenCalledWith("w1", "Icons", "f2");
  });

  it("moves a folder, offering neither itself nor its descendants as a target", async () => {
    setup("member", [
      ...FOLDERS,
      { id: "f3", workspace_id: "w1", parent_folder_id: "f2", name: "Icons" },
    ]);
    await screen.findByText("📁 Design");
    vi.mocked(foldersApi.move).mockResolvedValue(FOLDERS[1]);
    await userEvent.click(screen.getByLabelText("Move Design"));
    const select = await screen.findByLabelText("Destination folder");
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(options).toEqual(["Workspace root", "Contracts"]);
    await userEvent.selectOptions(select, "f1");
    await userEvent.click(screen.getByRole("button", { name: "Move here" }));
    expect(foldersApi.move).toHaveBeenCalledWith("f2", "f1");
  });

  it("links to the trash for members and not for guests", async () => {
    const { unmount } = setup("member");
    expect(await screen.findByText("🗑 Trash")).toBeInTheDocument();
    unmount();
    setup("guest");
    await screen.findByText("📄 All Documents");
    expect(screen.queryByText("🗑 Trash")).not.toBeInTheDocument();
  });
});
