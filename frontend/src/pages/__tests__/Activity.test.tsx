import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ActivityLogEntry } from "@/types";
import { ActivityPage } from "../Activity";
import { describeActivity } from "../activityText";

const state = vi.hoisted(() => ({ myRole: "admin" as string }));
const list = vi.hoisted(() => vi.fn());

vi.mock("@/workspace/WorkspaceContext", () => ({ useWorkspace: () => ({ myRole: state.myRole }) }));
vi.mock("@/components/Sidebar", () => ({ Sidebar: () => null }));
vi.mock("@/api/activity", () => ({ activityApi: { list } }));

const entry = (over: Partial<ActivityLogEntry>): ActivityLogEntry => ({
  id: "a1",
  actor_id: "u1",
  actor_name: "Ada",
  action: "workspace.created",
  target_type: null,
  target_id: null,
  metadata: {},
  created_at: "2026-09-21T10:00:00Z",
  ...over,
});

function renderPage() {
  return render(
    <MemoryRouter>
      <ActivityPage />
    </MemoryRouter>,
  );
}

describe("ActivityPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.myRole = "admin";
  });

  it("lists entries as readable sentences", async () => {
    list.mockResolvedValue({
      items: [
        entry({
          id: "1",
          action: "member.role_changed",
          metadata: { from: "member", to: "admin" },
        }),
        entry({ id: "2", actor_name: "Bo", action: "guest.document_granted" }),
        entry({ id: "3", actor_name: "Cy", action: "share_link.updated" }),
      ],
      page: 1,
      total: 2,
    });
    renderPage();
    expect(
      await screen.findByText(/changed a member's role \(member → admin\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/gave a guest access to a document/)).toBeInTheDocument();
    expect(screen.getByText("Bo")).toBeInTheDocument();
    expect(screen.getByText(/changed a share link's settings/)).toBeInTheDocument();
  });

  it("does not even ask the server when the role can't view the log", () => {
    state.myRole = "member";
    renderPage();
    expect(screen.getByText(/Only Admins and Owners/)).toBeInTheDocument();
    expect(list).not.toHaveBeenCalled();
  });

  it("shows an empty state and pages through long histories", async () => {
    list.mockResolvedValueOnce({ items: [], page: 1, total: 0 });
    const { unmount } = renderPage();
    expect(await screen.findByText("No activity yet.")).toBeInTheDocument();
    unmount();

    list.mockResolvedValue({ items: [entry({ id: "x" })], page: 1, total: 120 });
    renderPage();
    await screen.findByText("Page 1 of 3");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(list).toHaveBeenLastCalledWith("", 2);
  });

  it("falls back to the raw action name for unknown events", () => {
    expect(describeActivity(entry({ action: "something.new" }))).toBe("something.new");
  });
});
