import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiClientError,
  apiClient,
  errorMessage,
  setAuthToken,
  setUnauthorizedHandler,
} from "../client";

const fetchMock = vi.fn();

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  setAuthToken(null);
  setUnauthorizedHandler(null);
});

describe("apiClient requests", () => {
  it("builds the URL from the base path and drops undefined query values", async () => {
    fetchMock.mockResolvedValue(json(200, { items: [] }));
    await apiClient.get("/documents", { workspace_id: "w1", q: undefined, page: 2 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/v1/documents?");
    expect(url).toContain("workspace_id=w1");
    expect(url).toContain("page=2");
    expect(url).not.toContain("q=");
    expect(init.method).toBe("GET");
    expect(init.headers).not.toHaveProperty("Content-Type");
  });

  it("sends JSON bodies with a content type", async () => {
    fetchMock.mockResolvedValue(json(200, { id: "x" }));
    await apiClient.post("/workspaces", { name: "Acme" });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ name: "Acme" }));
  });

  it("attaches the bearer token once one is set, and stores it", async () => {
    fetchMock.mockResolvedValue(json(200, {}));
    setAuthToken("tok123");
    await apiClient.get("/auth/me");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer tok123");
    expect(localStorage.getItem("docvault_token")).toBe("tok123");
  });

  it("returns undefined for 204 responses", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiClient.delete("/share-links/l1")).resolves.toBeUndefined();
  });
});

describe("apiClient errors", () => {
  it("maps the API error envelope to an ApiClientError", async () => {
    fetchMock.mockResolvedValue(
      json(403, { error: { code: "FORBIDDEN", message: "Admins only" } }),
    );
    const err = await apiClient.get("/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiClientError);
    expect(err).toMatchObject({ status: 403, code: "FORBIDDEN", message: "Admins only" });
  });

  it("falls back to a generic message when the body is not an error envelope", async () => {
    fetchMock.mockResolvedValue(new Response("boom", { status: 500 }));
    await expect(apiClient.get("/x")).rejects.toMatchObject({
      status: 500,
      code: "UNKNOWN_ERROR",
      message: "Request failed with status 500",
    });
  });

  it("drops the session on a 401 that carried a token", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    setAuthToken("expired");
    fetchMock.mockResolvedValue(json(401, { error: { code: "UNAUTHORIZED", message: "Expired" } }));
    await expect(apiClient.get("/auth/me")).rejects.toBeInstanceOf(ApiClientError);
    expect(handler).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem("docvault_token")).toBeNull();
  });

  it("does not treat a wrong password (401 without a token) as an expired session", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    fetchMock.mockResolvedValue(
      json(401, { error: { code: "BAD_CREDENTIALS", message: "Wrong email or password" } }),
    );
    await expect(apiClient.post("/auth/login", {})).rejects.toBeInstanceOf(ApiClientError);
    expect(handler).not.toHaveBeenCalled();
  });
});

describe("errorMessage", () => {
  it("uses the API message, a network hint, or a generic fallback", () => {
    expect(errorMessage(new ApiClientError(400, "X", "Nope"))).toBe("Nope");
    expect(errorMessage(new TypeError("Failed to fetch"))).toMatch(/can't reach the server/i);
    expect(errorMessage(new Error("Upload to storage failed"))).toBe("Upload to storage failed");
    expect(errorMessage("weird")).toBe("Something went wrong. Try again.");
  });
});
