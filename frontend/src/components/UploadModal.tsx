import { useRef, useState } from "react";
import { Modal } from "./Modal";
import { documentsApi } from "@/api/documents";
import { errorMessage } from "@/api/client";
import { MAX_UPLOAD_MB } from "@/config";
import { useToast } from "@/hooks/useToast";
import type { Document } from "@/types";

interface UploadModalProps {
  workspaceId: string;
  folderId: string | null;
  onClose: () => void;
  onUploaded: (doc: Document) => void;
}

export function UploadModal({ workspaceId, folderId, onClose, onUploaded }: UploadModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  function pickFile(f: File | null) {
    setError(null);
    if (f && f.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setError(`"${f.name}" is over the ${MAX_UPLOAD_MB} MB limit — pick a smaller file.`);
      setFile(null);
      return;
    }
    setFile(f);
  }

  async function confirmUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const doc = await documentsApi.upload(file, { workspaceId, folderId });
      toast("Document uploaded — visible only to you until shared");
      onUploaded(doc);
      onClose();
    } catch (err) {
      // show the real reason (too large, not allowed, storage rejected it...) instead of a guess
      setError(errorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  return (
    <Modal title="Upload document" onClose={onClose}>
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          pickFile(e.dataTransfer.files[0] ?? null);
        }}
        style={{
          border: "1.5px dashed var(--color-border)",
          borderRadius: "var(--radius-md)",
          padding: "32px 16px",
          textAlign: "center",
          color: "var(--color-text-secondary)",
          marginBottom: 16,
          fontSize: 13,
          cursor: "pointer",
        }}
      >
        <input
          ref={inputRef}
          type="file"
          hidden
          aria-label="Choose a file"
          onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
        />
        <span style={{ fontSize: 22, display: "block", marginBottom: 6 }}>⬆</span>
        {file ? <strong>{file.name}</strong> : "Drag & drop a file, or click to browse"}
        <div style={{ fontSize: 11, marginTop: 4 }}>Max file size: {MAX_UPLOAD_MB} MB</div>
      </div>

      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
        <button className="btn btn-secondary btn-block" onClick={onClose}>
          Cancel
        </button>
        <button
          className="btn btn-primary btn-block"
          disabled={!file || uploading}
          onClick={confirmUpload}
        >
          {uploading ? "Uploading…" : "Upload"}
        </button>
      </div>
    </Modal>
  );
}
