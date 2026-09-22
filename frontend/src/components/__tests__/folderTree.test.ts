import { describe, expect, it } from "vitest";
import type { Folder } from "@/types";
import { folderPaths, subtreeIds } from "../folderTree";

const folder = (id: string, name: string, parent: string | null): Folder => ({
  id,
  workspace_id: "w1",
  parent_folder_id: parent,
  name,
});

const TREE = [
  folder("a", "A", null),
  folder("b", "B", "a"),
  folder("c", "C", "b"),
  folder("d", "D", null),
];

describe("folderTree", () => {
  it("labels folders with their full path", () => {
    const paths = folderPaths(TREE);
    expect(paths.get("c")).toBe("A / B / C");
    expect(paths.get("d")).toBe("D");
  });

  it("finds a folder and everything below it, and nothing else", () => {
    expect([...subtreeIds(TREE, "a")].sort()).toEqual(["a", "b", "c"]);
    expect([...subtreeIds(TREE, "d")]).toEqual(["d"]);
  });

  it("does not loop forever on a broken (cyclic) list", () => {
    const cyclic = [folder("x", "X", "y"), folder("y", "Y", "x")];
    expect(folderPaths(cyclic).get("x")?.length).toBeGreaterThan(0);
    expect(subtreeIds(cyclic, "x").size).toBe(2);
  });
});
