import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { LoginPage } from "../Login";

const login = vi.hoisted(() => vi.fn());
vi.mock("@/auth/AuthContext", () => ({ useAuth: () => ({ login }) }));

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/workspaces" element={<p>workspaces page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function fillAndSubmit() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), "ana@acme.com");
  await user.type(screen.getByLabelText("Password"), "hunter2hunter2");
  await user.click(screen.getByRole("button", { name: "Log In" }));
}

describe("LoginPage", () => {
  beforeEach(() => {
    login.mockReset();
  });

  it("signs in and goes to the workspace list", async () => {
    login.mockResolvedValue(undefined);
    renderLogin();
    await fillAndSubmit();
    expect(login).toHaveBeenCalledWith("ana@acme.com", "hunter2hunter2");
    expect(await screen.findByText("workspaces page")).toBeInTheDocument();
  });

  it("shows the API's message and stays on the page when sign-in fails", async () => {
    login.mockRejectedValue(new ApiClientError(401, "BAD_CREDENTIALS", "Wrong email or password"));
    renderLogin();
    await fillAndSubmit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong email or password");
    expect(screen.queryByText("workspaces page")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log In" })).toBeEnabled();
  });

  it("shows a generic message for an unexpected error", async () => {
    login.mockRejectedValue(new Error("kaboom"));
    renderLogin();
    await fillAndSubmit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
  });
});
