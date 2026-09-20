import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import type { Role, Workspace } from "@/types";
import { WorkspaceProvider, useWorkspace } from "../WorkspaceContext";

const api = vi.hoisted(() => ({ get: vi.fn(), list: vi.fn() }));
vi.mock("@/api/workspaces", () => ({ workspacesApi: { get: api.get } }));
vi.mock("@/api/members", () => ({ membersApi: { list: api.list } }));

function workspace(myRole: Role): Workspace {
  return { id: "w1", name: "Acme", owner_id: "u-owner", created_at: "", my_role: myRole };
}

function Probe() {
  const { loading, error, myRole, members } = useWorkspace();
  if (loading) return <p>loading</p>;
  if (error) return <p role="alert">{error}</p>;
  return (
    <p>
      role={myRole} members={members.length}
    </p>
  );
}

function renderProvider() {
  return render(
    <WorkspaceProvider workspaceId="w1">
      <Probe />
    </WorkspaceProvider>,
  );
}

describe("WorkspaceProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.list.mockResolvedValue([{ user_id: "a" }, { user_id: "b" }]);
  });

  it("takes the user's role from the workspace itself", async () => {
    api.get.mockResolvedValue(workspace("admin"));
    renderProvider();
    expect(await screen.findByText("role=admin members=2")).toBeInTheDocument();
  });

  it("lets a Guest open the workspace WITHOUT fetching the member list they are not allowed to see", async () => {
    api.get.mockResolvedValue(workspace("guest"));
    renderProvider();
    expect(await screen.findByText("role=guest members=0")).toBeInTheDocument();
    expect(api.list).not.toHaveBeenCalled();
  });

  it.each(["owner", "admin", "member"] as const)(
    "fetches the member list for a %s",
    async (role) => {
      api.get.mockResolvedValue(workspace(role));
      renderProvider();
      await screen.findByText(`role=${role} members=2`);
      expect(api.list).toHaveBeenCalledWith("w1");
    },
  );

  it("shows the reason when the workspace cannot be loaded", async () => {
    api.get.mockRejectedValue(new ApiClientError(404, "NOT_FOUND", "Workspace not found."));
    renderProvider();
    expect(await screen.findByRole("alert")).toHaveTextContent("Workspace not found.");
  });
});
