# DocVault — User Guide

What to do, step by step, for each thing DocVault does. For what the product is and how it is built, see [README.md](README.md) and [PRD/](PRD/README.md).

## Contents

1. [Create an account and sign in](#1-create-an-account-and-sign-in)
2. [Forgot your password](#2-forgot-your-password)
3. [Workspaces](#3-workspaces)
4. [Folders](#4-folders)
5. [Documents: upload, versions, organize](#5-documents-upload-versions-organize)
6. [Trash and restore](#6-trash-and-restore)
7. [Share a document by link](#7-share-a-document-by-link)
8. [Members, roles and invites](#8-members-roles-and-invites)
9. [Activity log](#9-activity-log)
10. [Roles at a glance](#10-roles-at-a-glance)

---

## 1. Create an account and sign in

1. Open the app and go to **Sign up**. Enter your name, email and a password (8–128 characters).
2. DocVault emails a confirmation link to that address. Until you open it, you can sign in, but nothing else works — you'll see a **"Confirm your email address"** screen with your email on it.
   - Didn't get the email? Click **Resend email** on that screen. You can ask again once a minute.
   - In a local/development setup with no email server configured, ask whoever runs it to check the API's log for the link instead.
3. Open the link in the email (`/verify-email/...`). It works once. After that, sign in normally and the app opens.

If an administrator invited you to a workspace, see [§8 Invites](#8-members-roles-and-invites) instead — you'll follow the invite link, which walks you through this same sign-up step.

**Your profile menu:** click your name at the bottom of the sidebar (or top of the workspace list) to see the email you're signed in as, and **Sign out**. Signing out ends the session immediately, on the server too — a copied link or saved token stops working right away.

## 2. Forgot your password

1. On the sign-in page, click **Forgot your password?**.
2. Enter your email and submit. DocVault always shows the same confirmation message, whether or not an account exists for that address — so this page never reveals who has an account.
3. If an account exists, an email arrives with a reset link. It works once and expires after an hour; asking again replaces the earlier link.
4. Open the link, choose a new password (typed twice, to catch typos), and submit. You're signed in with the new password from then on, and your email counts as confirmed if it wasn't already.

## 3. Workspaces

A workspace is a shared space for a team. You can belong to several.

- **See your workspaces:** the **workspaces** screen lists only the ones you're a member of — there's no way to browse or discover others.
- **Create one:** click **+ New workspace**, name it. You become its **Owner**.
- **Switch between them:** open a workspace, then use **← All workspaces** at the top of the sidebar to go back to the list.
- **Your role** for the open workspace is shown throughout the UI — it decides what you can do (see [§10](#10-roles-at-a-glance)).

> **Not currently in the app:** deleting a workspace. The backend supports it (Owner-only, and it's in the permission matrix), but there's no button for it yet in the UI — it can only be done by calling the API directly. If you need one gone, that's a gap to close before relying on it.

## 4. Folders

Folders organize documents inside a workspace. Anyone Member or above can see and manage them. **Guests never see folders at all** — not even that they exist — since a Guest's access is granted per document, not per folder (see [§8](#8-members-roles-and-invites)); a Guest's dashboard just shows the flat list of documents shared with them.

- **Create one:** **+ New folder** at the bottom of the folder list makes one at the workspace's top level. Click the **+** next to an existing folder to create one inside it.
- **Rename:** the pencil icon next to a folder.
- **Move:** the ↪ icon next to a folder — pick a new parent (or "Workspace root") from the list. A folder can't be moved into itself or into one of its own subfolders.
- **Delete:** the trash icon, with a confirmation. Deleting a folder never deletes what's inside it — its documents and subfolders move up one level, to the folder's own parent (or the root). If that would create a naming clash, the moved item is renamed with "(moved 2)", "(moved 3)", and so on, so nothing is silently overwritten.

## 5. Documents: upload, versions, organize

### Upload

Click **↑ Upload** (top right, when you have permission), then drag a file in or click to browse. DocVault checks the file's real content, not just its name — an oversized file, or one whose content doesn't match what it claims to be, is rejected with a reason.

### Search

Type into the search box above the document list. It matches by filename or by who uploaded it, and narrows to whichever folder you're viewing.

### Per-document actions

Each row in the document list has:

| Action | What it does |
|---|---|
| **Versions** | Shows the full upload history, newest first, with who uploaded each one and when. Any version can be downloaded, not just the current one. |
| **New version** | Uploads a replacement file. The old ones aren't lost — see Versions. |
| **Rename** | Changes the display name (not the stored file). |
| **Move** | Moves the document to a different folder, or to the workspace root. |
| **View** | Opens the document inline in the app, without downloading it — for common, safe-to-render types (PDF, PNG, JPEG, GIF, WebP, plain text). Click the document's own name for the same thing; a name that isn't clickable means that type can't be previewed. |
| **Download** | Downloads the current version. |
| **Share** | See [§7](#7-share-a-document-by-link) — only if your role allows sharing. |
| **Delete** | Moves the document to the trash (see [§6](#6-trash-and-restore)) — it is not deleted right away. |

A colored badge on each document shows whether it's private to you, visible to the workspace, or shared publicly by a link.

> **Not currently in the app:** a personal, outside-any-workspace document space. The backend supports uploading a document that belongs to you alone rather than to a workspace, but every screen in the app works inside a workspace, so there's no way to reach that from the UI today — everything you upload here lives in a workspace.

## 6. Trash and restore

- Deleting a document doesn't erase it immediately — it moves to the workspace's **Trash** (link in the sidebar, Member and above).
- From Trash, click **Restore** to bring a document back exactly where it was — unless its folder was also deleted in the meantime, in which case it comes back at the workspace root instead.
- A document stays in the trash for **30 days**. After that a background job removes it for good, along with its file and any share links pointing at it. There's no way to bring it back once that happens, so restore anything you need before the 30 days are up.

## 7. Share a document by link

Anyone Member or above can share a document they can see (never Guests).

1. Click **Share** on a document.
2. Choose the link's options before creating it:
   - **Allow download** — off means recipients can only view it in the browser, not save it (for file types that can be viewed at all; see below). **This one can be changed at any time after the link exists**, from the same modal — the address itself never changes when you flip it.
   - **Require password** — adds a password prompt before the document opens. Fixed once the link is created; revoke and make a new one to change it.
   - **Set expiry** — the link stops working after 30 days; turn it off for a link with no expiry. Also fixed once the link is created.
3. Click **Generate link**. The address is shown once, with a **Copy** button — DocVault doesn't store it in a form that can be shown again, so copy it now. Send it however you like; the recipient needs no DocVault account.
4. The modal also shows the **5 most recent times** the link was opened, so you can see whether it's being used.
5. To stop a link working, click **Revoke link**. This takes effect immediately, even for someone with the link already open.

**What a recipient sees:** just that one document — its name, size and type — with **View** and/or **Download** buttons, depending on what you allowed. Only common, safe-to-render file types (PDF, PNG, JPEG, GIF, WebP, plain text) offer a browser preview; everything else is download-only. If you turned download off *and* the file is a type that can't be previewed, the recipient sees neither button — just a note explaining why, so it's worth checking a link works before sending it for that combination. If a link is password-protected, they're asked for it before anything else is shown. A wrong password ten times in a row from the same place locks that link out for 15 minutes.

## 8. Members, roles and invites

*Admin and Owner only, unless noted.*

### Inviting someone

1. On the **Members & Roles** page, click **+ Invite**.
2. Enter their email and pick a role (**Admin**, **Member** or **Guest** — never Owner; ownership only moves by the explicit transfer below).
3. If you chose **Guest**, tick which individual documents they should be able to see — a Guest is scoped to specific documents, never to a folder (see [§4](#4-folders)). You can also grant or revoke documents later, from the member list.
4. Click **Send invite**. DocVault emails the invitation. It also shows you the link and a **Copy** button right away — if the email doesn't arrive, send that link yourself.
5. The invite appears under **Pending invitations** until it's accepted; click **Revoke** there to cancel it.

### Accepting an invite

Following the link: if you don't already have a DocVault account, it offers **Create account** or **Sign in**, and brings you straight back to accept afterward. Only the email address the invite was sent to can accept it. Invites expire after 7 days.

### Managing existing members

- **Change a role:** pick from the dropdown next to their name (never for the Owner).
- **Grant/revoke a Guest's documents:** click a document's chip next to a Guest's name to toggle it on or off. Takes effect immediately. **Moving that document to a different folder revokes the grant** — this is intentional (an access grant is pinned to where the document was when it was granted), so re-grant it afterward if you still want the Guest to see it there.
- **Remove someone:** click **Remove**. Their access to everything in the workspace ends at once (never for the Owner — remove them by first transferring ownership).
- **Transfer ownership:** click **Make Owner** next to an existing Admin. You become an Admin yourself; a workspace always has exactly one Owner.

## 9. Activity log

Admin and Owner only. The **Activity** page (sidebar) lists everything that's happened in the workspace — members invited or joining, roles changed, people removed, ownership transferred, a guest's document grants and revocations, share links created, changed or revoked — newest first, with who did it and when.

## 10. Roles at a glance

| Can... | Guest | Member | Admin | Owner |
|---|:---:|:---:|:---:|:---:|
| View documents individually granted to them | ✅ | — | — | — |
| View everything in the workspace, including all folders | — | ✅ | ✅ | ✅ |
| Upload, rename, move, delete documents; create/rename/move/delete folders; create share links | ❌ | ✅ | ✅ | ✅ |
| See the member list | ❌ | ✅ | ✅ | ✅ |
| Invite members, grant/revoke a guest's documents, view the activity log | ❌ | ❌ | ✅ | ✅ |
| Change roles, remove members (never the Owner) | ❌ | ❌ | ✅ | ✅ |
| Transfer ownership | ❌ | ❌ | ❌ | ✅ |
| Delete the workspace | ❌ | ❌ | ❌ | ✅ *(in the permission matrix; no button in the UI yet — see [§3](#3-workspaces))* |

A Guest sees only the individual documents explicitly granted to them — never any folder, never the rest of the workspace, and not even the fact that folders exist. Moving a granted document to a different folder revokes the grant; the person who granted it needs to grant it again.
