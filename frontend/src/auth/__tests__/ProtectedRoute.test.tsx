import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProtectedRoute } from "../ProtectedRoute";

const auth = vi.hoisted(() => ({ value: { user: null as unknown, loading: false } }));
vi.mock("../AuthContext", () => ({ useAuth: () => auth.value }));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<p>login page</p>} />
        <Route
          path="/private"
          element={
            <ProtectedRoute>
              <p>secret</p>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  beforeEach(() => {
    auth.value = { user: null, loading: false };
  });

  it("sends an anonymous visitor to the login page", () => {
    renderAt("/private");
    expect(screen.getByText("login page")).toBeInTheDocument();
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("renders nothing while the session is still being restored", () => {
    auth.value = { user: null, loading: true };
    renderAt("/private");
    expect(screen.queryByText("login page")).not.toBeInTheDocument();
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("renders the page for a signed-in user", () => {
    auth.value = { user: { id: "u1", email_verified: true }, loading: false };
    renderAt("/private");
    expect(screen.getByText("secret")).toBeInTheDocument();
  });

  it("holds back the page until the email address is confirmed (FR-1)", () => {
    auth.value = {
      user: { id: "u1", email: "ana@acme.com", email_verified: false },
      loading: false,
    };
    renderAt("/private");
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
    expect(screen.getByText("Confirm your email address")).toBeInTheDocument();
    expect(screen.getByText("ana@acme.com")).toBeInTheDocument();
  });
});
