import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Folder, Role, WorkspaceMember } from "@/types";
import { Sidebar } from "../Sidebar";

const FOLDERS: Folder[] = [
  { id: "f1", workspace_id: "w1", parent_folder_id: null, name: "Contracts" },
  { id: "f2", workspace_id: "w1", parent_folder_id: null, name: "Design" },
  { id: "f3", workspace_id: "w1", parent_folder_id: null, name: "Payroll" },
];

const state = vi.hoisted(() => ({
  userId: "u2",
  myRole: "guest" as string,
  members: [] as unknown[],
}));

vi.mock("@/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: state.userId } }) }));
vi.mock("@/workspace/WorkspaceContext", () => ({
  useWorkspace: () => ({
    workspace: { id: "w1", name: "Acme" },
    myRole: state.myRole,
    members: state.members,
  }),
}));
vi.mock("@/api/folders", () => ({ foldersApi: { list: vi.fn() } }));

import { foldersApi } from "@/api/folders";

function setup(userId: string, role: Role, members: WorkspaceMember[]) {
  state.userId = userId;
  state.myRole = role;
  state.members = members;
  vi.mocked(foldersApi.list).mockResolvedValue(FOLDERS);
  return render(
    <MemoryRouter>
      <Sidebar workspaceId="w1" />
    </MemoryRouter>,
  );
}

const guest = (id: string, granted: string[]): WorkspaceMember => ({
  user_id: id,
  name: id,
  email: "",
  role: "guest",
  joined_at: "",
  granted_folder_ids: granted,
});

describe("Sidebar folder scoping", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a guest ONLY their own granted folders, never another guest's", async () => {
    // u1 (first guest in the list) was granted Contracts; the signed-in guest u2 only Design.
    setup("u2", "guest", [guest("u1", ["f1"]), guest("u2", ["f2"])]);
    expect(await screen.findByText("📁 Design")).toBeInTheDocument();
    expect(screen.queryByText("📁 Contracts")).not.toBeInTheDocument();
    expect(screen.queryByText("📁 Payroll")).not.toBeInTheDocument();
  });

  it("shows a guest with no grants no folders at all", async () => {
    setup("u2", "guest", [guest("u2", [])]);
    await screen.findByText("📄 All Documents");
    expect(screen.queryByText(/📁/)).not.toBeInTheDocument();
  });

  it("shows every folder to a Member, plus the Members link; a Guest has no Members link", async () => {
    const { unmount } = setup("u3", "member", []);
    expect(await screen.findByText("📁 Payroll")).toBeInTheDocument();
    expect(screen.getByText("📁 Contracts")).toBeInTheDocument();
    expect(screen.getByText("👥 Members & Roles")).toBeInTheDocument();
    unmount();

    setup("u2", "guest", [guest("u2", ["f2"])]);
    await screen.findByText("📁 Design");
    expect(screen.queryByText("👥 Members & Roles")).not.toBeInTheDocument();
  });
});
