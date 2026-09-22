import type { Folder } from "@/types";

// "Parent / Child" labels so two folders with the same name stay distinguishable.
export function folderPaths(folders: Folder[]): Map<string, string> {
  const byId = new Map(folders.map((f) => [f.id, f]));
  const paths = new Map<string, string>();
  for (const folder of folders) {
    const parts: string[] = [];
    let node: Folder | undefined = folder;
    for (let depth = 0; node && depth < 25; depth++) {
      parts.unshift(node.name);
      node = node.parent_folder_id ? byId.get(node.parent_folder_id) : undefined;
    }
    paths.set(folder.id, parts.join(" / "));
  }
  return paths;
}

// Ids of a folder and everything below it: a folder can't be moved into any of these.
export function subtreeIds(folders: Folder[], rootId: string): Set<string> {
  const ids = new Set([rootId]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const f of folders) {
      if (f.parent_folder_id && ids.has(f.parent_folder_id) && !ids.has(f.id)) {
        ids.add(f.id);
        grew = true;
      }
    }
  }
  return ids;
}
