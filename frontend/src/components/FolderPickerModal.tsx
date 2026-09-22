import { useState } from "react";
import { Modal } from "./Modal";
import { folderPaths } from "@/components/folderTree";
import type { Folder } from "@/types";

interface Props {
  title: string;
  folders: Folder[];
  /** folders that can't be chosen (a folder itself and its descendants) */
  excludeIds?: Set<string>;
  currentId: string | null;
  onPick: (folderId: string | null) => void | Promise<void>;
  onClose: () => void;
}

export function FolderPickerModal({
  title,
  folders,
  excludeIds,
  currentId,
  onPick,
  onClose,
}: Props) {
  const [choice, setChoice] = useState<string>(currentId ?? "");
  const [busy, setBusy] = useState(false);
  const paths = folderPaths(folders);
  const options = folders
    .filter((f) => !excludeIds?.has(f.id))
    .map((f) => ({ id: f.id, label: paths.get(f.id) ?? f.name }))
    .sort((a, b) => a.label.localeCompare(b.label));

  async function submit() {
    setBusy(true);
    try {
      await onPick(choice === "" ? null : choice);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={title} onClose={onClose}>
      <label style={{ display: "block", fontSize: 12, marginBottom: 6 }} htmlFor="destination">
        Destination
      </label>
      <select
        id="destination"
        aria-label="Destination folder"
        value={choice}
        onChange={(e) => setChoice(e.target.value)}
        style={{ width: "100%", padding: 8, marginBottom: 16 }}
      >
        <option value="">Workspace root</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button className="btn" onClick={onClose}>
          Cancel
        </button>
        <button
          className="btn btn-primary"
          disabled={busy || choice === (currentId ?? "")}
          onClick={submit}
        >
          Move here
        </button>
      </div>
    </Modal>
  );
}
