import { describe, expect, it } from "vitest";
import { safeNextPath } from "../nextPath";

describe("safeNextPath", () => {
  it("keeps paths inside the app", () => {
    expect(safeNextPath("/invites/abc")).toBe("/invites/abc");
    expect(safeNextPath("/workspaces/w1?x=1")).toBe("/workspaces/w1?x=1");
  });

  it.each([
    null,
    "",
    "https://evil.example/",
    "//evil.example/",
    "/\\evil.example",
    "javascript:alert(1)",
    "workspaces",
  ])("rejects %j, so a login link can't bounce someone to another site", (value) => {
    expect(safeNextPath(value)).toBeNull();
  });
});
