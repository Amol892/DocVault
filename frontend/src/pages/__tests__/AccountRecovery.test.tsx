import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { ForgotPasswordPage } from "../ForgotPassword";
import { ResetPasswordPage } from "../ResetPassword";
import { VerifyEmailPage } from "../VerifyEmail";

const authApi = vi.hoisted(() => ({
  verifyEmail: vi.fn(),
  forgotPassword: vi.fn(),
  resetPassword: vi.fn(),
}));
vi.mock("@/api/auth", () => ({ authApi }));

describe("VerifyEmailPage", () => {
  beforeEach(() => vi.clearAllMocks());

  function renderPage() {
    return render(
      <StrictMode>
        <MemoryRouter initialEntries={["/verify-email/tok1"]}>
          <Routes>
            <Route path="/verify-email/:token" element={<VerifyEmailPage />} />
          </Routes>
        </MemoryRouter>
      </StrictMode>,
    );
  }

  it("confirms the address, sending the single-use token only once even under StrictMode", async () => {
    authApi.verifyEmail.mockResolvedValue(undefined);
    renderPage();
    expect(await screen.findByText("Email confirmed")).toBeInTheDocument();
    expect(authApi.verifyEmail).toHaveBeenCalledTimes(1);
    expect(authApi.verifyEmail).toHaveBeenCalledWith("tok1");
    expect(screen.getByRole("link", { name: "Continue" })).toHaveAttribute("href", "/workspaces");
  });

  it("explains an invalid or used link and points to signing in for a new one", async () => {
    authApi.verifyEmail.mockRejectedValue(
      new ApiClientError(400, "INVALID_TOKEN", "This link is invalid or has expired."),
    );
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("ForgotPasswordPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("asks for a link and gives the same answer for any address", async () => {
    authApi.forgotPassword.mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByLabelText("Email"), " someone@example.com ");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(authApi.forgotPassword).toHaveBeenCalledWith("someone@example.com");
    expect(await screen.findByRole("status")).toHaveTextContent(/If an account exists/);
  });

  it("shows a failure to reach the server", async () => {
    authApi.forgotPassword.mockRejectedValue(new Error("Can't reach the server."));
    render(
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByLabelText("Email"), "a@b.co");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the server.");
  });
});

describe("ResetPasswordPage", () => {
  beforeEach(() => vi.clearAllMocks());

  function renderPage() {
    return render(
      <MemoryRouter initialEntries={["/reset-password/tok9"]}>
        <Routes>
          <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("won't send two different passwords", async () => {
    renderPage();
    await userEvent.type(screen.getByLabelText("New password"), "first-password");
    await userEvent.type(screen.getByLabelText("Repeat the password"), "second-password");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("don't match");
    expect(authApi.resetPassword).not.toHaveBeenCalled();
  });

  it("changes the password with the emailed token and offers sign in", async () => {
    authApi.resetPassword.mockResolvedValue(undefined);
    renderPage();
    await userEvent.type(screen.getByLabelText("New password"), "a-new-password");
    await userEvent.type(screen.getByLabelText("Repeat the password"), "a-new-password");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(authApi.resetPassword).toHaveBeenCalledWith("tok9", "a-new-password");
    expect(await screen.findByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  it("shows why an expired or used link failed and keeps the form", async () => {
    authApi.resetPassword.mockRejectedValue(
      new ApiClientError(400, "INVALID_TOKEN", "This link is invalid or has expired."),
    );
    renderPage();
    await userEvent.type(screen.getByLabelText("New password"), "a-new-password");
    await userEvent.type(screen.getByLabelText("Repeat the password"), "a-new-password");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
    expect(screen.getByLabelText("New password")).toBeInTheDocument();
  });
});
