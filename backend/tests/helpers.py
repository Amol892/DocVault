"""Small helpers shared by the API tests."""

from dataclasses import dataclass
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkspaceRole
from app.models.workspace import WorkspaceMember

API = "/api/v1"
PASSWORD = "correct-horse-battery"


@dataclass
class TestUser:
    __test__ = False  # not a pytest test class

    id: str
    email: str
    name: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


async def make_user(client: AsyncClient, email: str, name: str | None = None) -> TestUser:
    """Register and log in through the real API."""
    name = name or email.split("@")[0].title()
    registered = await client.post(
        f"{API}/auth/register", json={"email": email, "password": PASSWORD, "name": name}
    )
    assert registered.status_code == 201, registered.text
    login = await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    body = login.json()
    return TestUser(id=body["user"]["id"], email=email, name=name, token=body["token"])


async def make_workspace(
    client: AsyncClient, owner: TestUser, name: str = "Acme"
) -> dict[str, Any]:
    response = await client.post(f"{API}/workspaces", json={"name": name}, headers=owner.headers)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def add_member(
    db: AsyncSession, workspace_id: str, user: TestUser, role: WorkspaceRole
) -> None:
    """Add a member directly in the database. There is no invite endpoint yet."""
    db.add(WorkspaceMember(workspace_id=workspace_id, user_id=user.id, role=role))
    await db.commit()


async def workspace_with_roles(
    client: AsyncClient, db: AsyncSession
) -> tuple[dict[str, Any], dict[str, TestUser]]:
    """A workspace with one user per role: owner, admin, member, guest (plus `outsider`, who
    belongs to nothing)."""
    users = {
        role: await make_user(client, f"{role}@example.com")
        for role in ("owner", "admin", "member", "guest", "outsider")
    }
    workspace = await make_workspace(client, users["owner"])
    await add_member(db, workspace["id"], users["admin"], WorkspaceRole.ADMIN)
    await add_member(db, workspace["id"], users["member"], WorkspaceRole.MEMBER)
    await add_member(db, workspace["id"], users["guest"], WorkspaceRole.GUEST)
    return workspace, users
