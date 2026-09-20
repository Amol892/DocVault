import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { authApi } from "../auth";
import { setAuthToken } from "../client";

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  setAuthToken("tok-123");
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  setAuthToken(null);
});

describe("authApi.logout", () => {
  it("revokes the token on the server, sending it as the bearer credential", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await authApi.logout();

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/v1/auth/logout");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer tok-123");
  });

  it("forgets the token locally once the server has been told", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await authApi.logout();
    expect(localStorage.getItem("docvault_token")).toBeNull();
  });

  it("still signs the user out when the server is unreachable", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(authApi.logout()).resolves.toBeUndefined();
    expect(localStorage.getItem("docvault_token")).toBeNull();
  });

  it("still signs the user out when the token was already invalid", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: "UNAUTHORIZED", message: "Not authenticated." } }),
        {
          status: 401,
          headers: { "content-type": "application/json" },
        },
      ),
    );
    await expect(authApi.logout()).resolves.toBeUndefined();
    expect(localStorage.getItem("docvault_token")).toBeNull();
  });
});
