import { describe, it, expect } from "vitest";
import { hasLevel, can, guestCanSeeFolder, canActOnMember, roleLevel } from "../roleHierarchy";
import type { Role } from "@/types";

const ROLES: Role[] = ["owner", "admin", "member", "guest"];

describe("role hierarchy — inheritance actually holds", () => {
  it("each role's level is strictly greater than the one below it", () => {
    expect(roleLevel("owner")).toBeGreaterThan(roleLevel("admin"));
    expect(roleLevel("admin")).toBeGreaterThan(roleLevel("member"));
    expect(roleLevel("member")).toBeGreaterThan(roleLevel("guest"));
  });

  it("every higher role can do everything a lower role can (Owner ⊇ Admin ⊇ Member ⊇ Guest)", () => {
    const actions = [
      "VIEW_GRANTED_DOCS",
      "UPLOAD_DOCUMENT",
      "INVITE_MEMBER",
      "TRANSFER_OWNERSHIP",
    ] as const;
    for (const action of actions) {
      for (let i = 0; i < ROLES.length - 1; i++) {
        const higher = ROLES[i];
        const lower = ROLES[i + 1];
        if (can(lower, action)) {
          expect(
            can(higher, action),
            `${higher} should be able to do what ${lower} can (${action})`,
          ).toBe(true);
        }
      }
    }
  });

  it("only Owner can transfer ownership or delete the workspace", () => {
    expect(can("owner", "TRANSFER_OWNERSHIP")).toBe(true);
    expect(can("admin", "TRANSFER_OWNERSHIP")).toBe(false);
    expect(can("owner", "DELETE_WORKSPACE")).toBe(true);
    expect(can("admin", "DELETE_WORKSPACE")).toBe(false);
  });

  it("Guest passes the base view-level check but still needs a folder grant", () => {
    expect(hasLevel("guest", 1)).toBe(true);
    expect(guestCanSeeFolder("guest", "f1", undefined)).toBe(false);
    expect(guestCanSeeFolder("guest", "f1", ["f2"])).toBe(false);
    expect(guestCanSeeFolder("guest", "f1", ["f1", "f2"])).toBe(true);
  });

  it("Member/Admin/Owner are never folder-scoped — guestCanSeeFolder always passes for them", () => {
    expect(guestCanSeeFolder("member", "any-folder", undefined)).toBe(true);
    expect(guestCanSeeFolder("admin", "any-folder", undefined)).toBe(true);
    expect(guestCanSeeFolder("owner", "any-folder", undefined)).toBe(true);
  });

  it("an Admin (level 3, passes CHANGE_MEMBER_ROLE's floor) is still blocked from acting on the Owner", () => {
    expect(can("admin", "CHANGE_MEMBER_ROLE")).toBe(true); // the level check alone would allow it
    expect(canActOnMember("admin", "owner", "CHANGE_MEMBER_ROLE")).toBe(false); // the target guard blocks it
    expect(canActOnMember("admin", "owner", "REMOVE_MEMBER")).toBe(false);
  });

  it("an Admin can act on Members and Guests, just not the Owner", () => {
    expect(canActOnMember("admin", "member", "CHANGE_MEMBER_ROLE")).toBe(true);
    expect(canActOnMember("admin", "guest", "REMOVE_MEMBER")).toBe(true);
  });

  it("a Member cannot change roles or remove members at all, regardless of target", () => {
    expect(canActOnMember("member", "guest", "CHANGE_MEMBER_ROLE")).toBe(false);
    expect(canActOnMember("member", "member", "REMOVE_MEMBER")).toBe(false);
  });
});
