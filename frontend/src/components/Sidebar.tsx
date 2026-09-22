import { NavLink, useLocation, useNavigate, useParams } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import type { Folder } from "@/types";
import { foldersApi } from "@/api/folders";
import { useWorkspace } from "@/workspace/WorkspaceContext";
import { can } from "@/permissions/roleHierarchy";
import { useSafeAction } from "@/hooks/useSafeAction";
import { UserMenu } from "@/components/UserMenu";
import { FolderPickerModal } from "@/components/FolderPickerModal";
import { subtreeIds } from "@/components/folderTree";

// FR-21: the folder list is a Member-and-above concept — the API always returns it empty for a
// Guest, who instead sees a flat list of individually granted documents on the dashboard itself.
// This shows exactly what the API returns. Member and above may create, rename and delete.
export function Sidebar({ workspaceId }: { workspaceId: string }) {
  const { workspace, myRole } = useWorkspace();
  const navigate = useNavigate();
  const location = useLocation();
  const { folderId } = useParams();
  const safe = useSafeAction();
  const [folders, setFolders] = useState<Folder[]>([]);
  const [moving, setMoving] = useState<Folder | null>(null);

  const reload = useCallback(
    () => safe(() => foldersApi.list(workspaceId)).then((res) => (res.ok ? res.value : null)),
    [workspaceId, safe],
  );

  useEffect(() => {
    let cancelled = false;
    reload().then((list) => {
      if (!cancelled && list) setFolders(list);
    });
    return () => {
      cancelled = true;
    };
  }, [reload]);

  const canManage = myRole ? can(myRole, "CREATE_FOLDER") : false;

  async function refresh() {
    const list = await reload();
    if (list) setFolders(list);
  }

  async function createFolder(parent?: Folder) {
    const name = window.prompt(parent ? `New folder in ${parent.name}` : "Folder name")?.trim();
    if (!name) return;
    const res = await safe(() => foldersApi.create(workspaceId, name, parent?.id ?? null));
    if (res.ok) await refresh();
  }

  async function renameFolder(folder: Folder) {
    const name = window.prompt("Rename folder", folder.name)?.trim();
    if (!name || name === folder.name) return;
    const res = await safe(() => foldersApi.rename(folder.id, name));
    if (res.ok) await refresh();
  }

  async function moveFolder(target: string | null) {
    if (!moving) return;
    const res = await safe(() => foldersApi.move(moving.id, target));
    if (!res.ok) return;
    setMoving(null);
    await refresh();
  }

  async function deleteFolder(folder: Folder) {
    const ok = window.confirm(
      `Delete "${folder.name}"? Everything inside moves up one level; nothing is lost.`,
    );
    if (!ok) return;
    const res = await safe(() => foldersApi.delete(folder.id));
    if (!res.ok) return;
    if (folderId === folder.id) navigate(`/workspaces/${workspaceId}`);
    await refresh();
  }

  return (
    <div
      style={{
        width: 250,
        flexShrink: 0,
        background: "var(--color-bg-secondary)",
        padding: "20px 14px",
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      <button
        onClick={() => navigate("/workspaces")}
        style={{
          background: "transparent",
          border: "none",
          padding: "2px 10px",
          fontSize: 12,
          textAlign: "left",
          color: "var(--color-accent)",
        }}
      >
        ← All workspaces
      </button>
      <div
        title={workspace?.name}
        style={{
          padding: "6px 10px 12px",
          fontSize: 15,
          fontWeight: 600,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {workspace?.name ?? "…"}
      </div>

      <SidebarLink to={`/workspaces/${workspaceId}`} active={!folderId} label="📄 All Documents" />
      {folders.map((f) => (
        <div key={f.id} style={{ display: "flex", alignItems: "center", gap: 2 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <SidebarLink
              to={`/workspaces/${workspaceId}/folders/${f.id}`}
              active={folderId === f.id}
              label={`📁 ${f.name}`}
              indent={!!f.parent_folder_id}
            />
          </div>
          {canManage && (
            <>
              <IconButton label={`New folder in ${f.name}`} onClick={() => createFolder(f)}>
                +
              </IconButton>
              <IconButton label={`Move ${f.name}`} onClick={() => setMoving(f)}>
                ↪
              </IconButton>
              <IconButton label={`Rename ${f.name}`} onClick={() => renameFolder(f)}>
                ✎
              </IconButton>
              <IconButton label={`Delete ${f.name}`} onClick={() => deleteFolder(f)}>
                🗑
              </IconButton>
            </>
          )}
        </div>
      ))}
      {canManage && (
        <button
          onClick={() => createFolder()}
          style={{
            textAlign: "left",
            padding: "7px 10px",
            fontSize: 13,
            color: "var(--color-accent)",
            background: "transparent",
            border: "none",
          }}
        >
          + New folder
        </button>
      )}

      {myRole && can(myRole, "SEE_MEMBER_LIST") && (
        <>
          <div
            style={{
              fontSize: 10,
              textTransform: "uppercase",
              letterSpacing: "0.04em",
              color: "var(--color-text-secondary)",
              margin: "12px 0 2px 10px",
            }}
          >
            Workspace
          </div>
          <SidebarLink
            to={`/workspaces/${workspaceId}/trash`}
            active={location.pathname.endsWith("/trash")}
            label="🗑 Trash"
          />
          <SidebarLink
            to={`/workspaces/${workspaceId}/members`}
            active={location.pathname.endsWith("/members")}
            label="👥 Members & Roles"
          />
          {can(myRole, "VIEW_ACTIVITY_LOG") && (
            <SidebarLink
              to={`/workspaces/${workspaceId}/activity`}
              active={location.pathname.endsWith("/activity")}
              label="🕘 Activity"
            />
          )}
        </>
      )}

      {moving && (
        <FolderPickerModal
          title={`Move ${moving.name}`}
          folders={folders}
          excludeIds={subtreeIds(folders, moving.id)}
          currentId={moving.parent_folder_id}
          onPick={moveFolder}
          onClose={() => setMoving(null)}
        />
      )}

      <div style={{ marginTop: "auto", display: "flex", flexDirection: "column" }}>
        {myRole === "guest" && (
          <div
            style={{
              marginBottom: 8,
              background: "var(--color-guest-soft)",
              color: "var(--color-guest)",
              fontSize: 11,
              padding: "8px 10px",
              borderRadius: "var(--radius-sm)",
            }}
          >
            You're a Guest here — you can only see documents that were shared with you directly.
          </div>
        )}
        <UserMenu placement="up" />
      </div>
    </div>
  );
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      aria-label={label}
      title={label}
      onClick={onClick}
      style={{
        background: "transparent",
        border: "none",
        fontSize: 12,
        padding: "4px 5px",
        color: "var(--color-text-secondary)",
      }}
    >
      {children}
    </button>
  );
}

function SidebarLink({
  to,
  active,
  label,
  indent,
}: {
  to: string;
  active: boolean;
  label: string;
  indent?: boolean;
}) {
  return (
    <NavLink
      to={to}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "7px 10px",
        borderRadius: "var(--radius-sm)",
        fontSize: 13,
        textDecoration: "none",
        color: active ? "var(--color-accent)" : "var(--color-text-primary)",
        background: active ? "var(--color-accent-soft)" : "transparent",
        fontWeight: active ? 600 : 400,
        paddingLeft: indent ? 26 : 10,
      }}
    >
      {label}
    </NavLink>
  );
}
