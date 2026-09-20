import type { ReactNode } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { ToastContext } from "@/hooks/useToast";
import type { Role, WorkspaceMember } from "@/types";
import { MembersRolesPage } from "../MembersRoles";

const MEMBERS: WorkspaceMember[] = [
  { user_id: "u-owner", name: "Olivia Owner", email: "o@x.com", role: "owner", joined_at: "" },
  { user_id: "u-admin", name: "Adam Admin", email: "a@x.com", role: "admin", joined_at: "" },
  { user_id: "u-member", name: "Mia Member", email: "m@x.com", role: "member", joined_at: "" },
  { user_id: "u-guest", name: "Gus Guest", email: "g@x.com", role: "guest", joined_at: "" },
];

const workspace = vi.hoisted(() => ({
  value: {} as Record<string, unknown>,
}));
const membersApi = vi.hoisted(() => ({ remove: vi.fn(), changeRole: vi.fn() }));
const refreshMembers = vi.hoisted(() => vi.fn());
const toast = vi.hoisted(() => vi.fn());

vi.mock("@/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u-me" } }) }));
vi.mock("@/workspace/WorkspaceContext", () => ({ useWorkspace: () => workspace.value }));
vi.mock("@/components/Sidebar", () => ({ Sidebar: () => null }));
vi.mock("@/components/InviteModal", () => ({ InviteModal: () => null }));
vi.mock("@/api/folders", () => ({ foldersApi: { list: vi.fn().mockResolvedValue([]) } }));
vi.mock("@/api/workspaces", () => ({ workspacesApi: { transferOwnership: vi.fn() } }));
vi.mock("@/api/members", () => ({ membersApi }));

function renderAs(myRole: Role) {
  workspace.value = {
    workspace: { id: "w1", name: "Acme", owner_id: "u-owner", created_at: "" },
    members: MEMBERS,
    myRole,
    loading: false,
    error: null,
    refreshMembers,
  };
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ToastContext.Provider value={toast}>
      <MemoryRouter>{children}</MemoryRouter>
    </ToastContext.Provider>
  );
  return render(<MembersRolesPage />, { wrapper });
}

describe("MembersRolesPage permissions (PRD 06)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    refreshMembers.mockResolvedValue(undefined);
  });

  it("does not show the member list to a Guest", () => {
    renderAs("guest");
    expect(screen.getByText(/isn't available to Guests/i)).toBeInTheDocument();
    expect(screen.queryByText("Mia Member")).not.toBeInTheDocument();
  });

  it("shows a Member a read-only list, with no way to invite, change or remove", () => {
    renderAs("member");
    for (const m of MEMBERS) expect(screen.getByText(m.name)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ Invite" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Role for/)).not.toBeInTheDocument();
  });

  it("gives an Admin invite/change/remove, but never over the Owner and no ownership transfer", () => {
    renderAs("admin");
    expect(screen.getByRole("button", { name: "+ Invite" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(3); // not the owner
    expect(screen.getAllByLabelText(/^Role for/)).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Make Owner" })).not.toBeInTheDocument();
  });

  it("lets only the Owner promote an Admin to Owner", () => {
    renderAs("owner");
    expect(screen.getByRole("button", { name: "Make Owner" })).toBeInTheDocument();
  });
});

describe("MembersRolesPage failures", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    refreshMembers.mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("shows the server's reason when removing a member fails, and does not refresh", async () => {
    membersApi.remove.mockRejectedValue(new ApiClientError(403, "FORBIDDEN", "Not allowed"));
    renderAs("admin");
    const row = screen.getByText("Mia Member").closest("div")!.parentElement!.parentElement!;
    await userEvent.setup().click(within(row).getByRole("button", { name: "Remove" }));
    expect(membersApi.remove).toHaveBeenCalledWith("", "u-member");
    expect(toast).toHaveBeenCalledWith("Not allowed");
    expect(refreshMembers).not.toHaveBeenCalled();
  });

  it("refreshes the list after a successful removal", async () => {
    membersApi.remove.mockResolvedValue(undefined);
    renderAs("admin");
    const row = screen.getByText("Gus Guest").closest("div")!.parentElement!.parentElement!;
    await userEvent.setup().click(within(row).getByRole("button", { name: "Remove" }));
    expect(toast).toHaveBeenCalledWith("Gus Guest removed — access revoked");
    expect(refreshMembers).toHaveBeenCalledTimes(1);
  });
});
