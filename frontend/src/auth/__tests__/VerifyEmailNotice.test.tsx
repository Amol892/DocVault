import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { VerifyEmailNotice } from "../VerifyEmailNotice";

const auth = vi.hoisted(() => ({
  user: { id: "u1", email: "ana@acme.com", email_verified: false },
  logout: vi.fn(),
  refreshUser: vi.fn(),
}));
const authApi = vi.hoisted(() => ({ resendVerification: vi.fn() }));
vi.mock("../AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/api/auth", () => ({ authApi }));

describe("VerifyEmailNotice", () => {
  beforeEach(() => vi.clearAllMocks());

  it("resends the confirmation email", async () => {
    authApi.resendVerification.mockResolvedValue(undefined);
    render(<VerifyEmailNotice />);
    await userEvent.click(screen.getByRole("button", { name: "Resend email" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/on its way/);
  });

  it("shows the server's message when resending too soon", async () => {
    authApi.resendVerification.mockRejectedValue(
      new ApiClientError(
        429,
        "TOO_MANY_REQUESTS",
        "A verification email was just sent. Wait a minute.",
      ),
    );
    render(<VerifyEmailNotice />);
    await userEvent.click(screen.getByRole("button", { name: "Resend email" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wait a minute");
  });

  it("re-reads the account when asked, and says so if it is still unconfirmed", async () => {
    auth.refreshUser.mockResolvedValue(undefined);
    render(<VerifyEmailNotice />);
    await userEvent.click(screen.getByRole("button", { name: "I've confirmed it" }));
    expect(auth.refreshUser).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("status")).toHaveTextContent(/Not confirmed yet/);
  });

  it("lets the user sign out", async () => {
    render(<VerifyEmailNotice />);
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(auth.logout).toHaveBeenCalledTimes(1);
  });
});
