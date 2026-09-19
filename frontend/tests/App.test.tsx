import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "../src/App";

afterEach(() => vi.restoreAllMocks());

test("shows API status from /api/health", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok", database: "ok" }),
    }),
  );
  render(<App />);
  expect(await screen.findByText("ok")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith("/api/health", undefined);
});

test("shows unavailable when API fails", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
  render(<App />);
  expect(await screen.findByText("unavailable")).toBeInTheDocument();
});
