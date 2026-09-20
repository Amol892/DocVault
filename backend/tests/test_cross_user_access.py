"""Tenant isolation: what someone outside a workspace can and cannot learn about it.

This is the most important test file. The whole design relies on one shared check
(api/deps.py::get_workspace_access), so every workspace endpoint is exercised here.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import API, TestUser, make_user, make_workspace, workspace_with_roles

MISSING_WORKSPACE = "NoSuchWorkp"  # well-formed, but no such workspace
MISSING_USER = "NoSuchUser1"

# (method, path template, json body): every endpoint that takes a workspace id
WORKSPACE_ENDPOINTS = [
    ("GET", "/workspaces/{ws}", None),
    ("DELETE", "/workspaces/{ws}", None),
    ("GET", "/workspaces/{ws}/members", None),
    ("PATCH", "/workspaces/{ws}/members/{user}", {"role": "member"}),
    ("DELETE", "/workspaces/{ws}/members/{user}", None),
    ("POST", "/workspaces/{ws}/members/{user}/transfer-ownership", None),
]


def _url(template: str, workspace_id: str, user_id: str) -> str:
    return API + template.format(ws=workspace_id, user=user_id)


class TestOutsidersLearnNothing:
    @pytest.mark.parametrize(("method", "template", "body"), WORKSPACE_ENDPOINTS)
    async def test_a_non_member_gets_the_same_answer_as_for_a_workspace_that_does_not_exist(
        self,
        client: AsyncClient,
        db: AsyncSession,
        method: str,
        template: str,
        body: dict[str, str] | None,
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        outsider = users["outsider"]

        real = await client.request(
            method,
            _url(template, workspace["id"], users["member"].id),
            headers=outsider.headers,
            json=body,
        )
        fake = await client.request(
            method,
            _url(template, MISSING_WORKSPACE, users["member"].id),
            headers=outsider.headers,
            json=body,
        )

        assert real.status_code == fake.status_code == 404
        assert real.json() == fake.json(), "a non-member must not be able to tell the two apart"

    @pytest.mark.parametrize(("method", "template", "body"), WORKSPACE_ENDPOINTS)
    async def test_an_unauthenticated_request_is_rejected_before_anything_is_revealed(
        self,
        client: AsyncClient,
        db: AsyncSession,
        method: str,
        template: str,
        body: dict[str, str] | None,
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.request(
            method, _url(template, workspace["id"], users["member"].id), json=body
        )
        assert response.status_code == 401

    async def test_the_workspace_is_absent_from_an_outsiders_list(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        listing = await client.get(f"{API}/workspaces", headers=users["outsider"].headers)
        assert listing.json() == []
        assert workspace["id"] not in listing.text

    async def test_the_workspace_id_never_appears_in_an_outsiders_error(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        workspace, users = await workspace_with_roles(client, db)
        response = await client.get(
            f"{API}/workspaces/{workspace['id']}", headers=users["outsider"].headers
        )
        assert workspace["id"] not in response.text
        assert workspace["name"] not in response.text


class TestNoBleedBetweenWorkspaces:
    async def _two_workspaces(
        self, client: AsyncClient
    ) -> tuple[TestUser, TestUser, dict[str, str], dict[str, str]]:
        ana = await make_user(client, "ana@example.com")
        bob = await make_user(client, "bob@example.com")
        return (
            ana,
            bob,
            await make_workspace(client, ana, "Ana's"),
            await make_workspace(client, bob, "Bob's"),
        )

    async def test_being_owner_of_one_workspace_gives_nothing_in_another(
        self, client: AsyncClient
    ) -> None:
        ana, bob, _, bobs = await self._two_workspaces(client)
        for method, template, body in WORKSPACE_ENDPOINTS:
            response = await client.request(
                method, _url(template, bobs["id"], bob.id), headers=ana.headers, json=body
            )
            assert response.status_code == 404, f"{method} {template}"
        still_there = await client.get(f"{API}/workspaces/{bobs['id']}", headers=bob.headers)
        assert still_there.status_code == 200

    async def test_a_members_list_only_ever_contains_that_workspaces_members(
        self, client: AsyncClient
    ) -> None:
        ana, bob, anas, _ = await self._two_workspaces(client)
        response = await client.get(f"{API}/workspaces/{anas['id']}/members", headers=ana.headers)
        assert [m["user_id"] for m in response.json()] == [ana.id]
        assert bob.id not in response.text

    async def test_a_user_from_another_workspace_cannot_be_targeted(
        self, client: AsyncClient
    ) -> None:
        """Owner of A names a user id that only exists in B: that is 'no such member', not a hit."""
        ana, bob, anas, _ = await self._two_workspaces(client)
        for method, template, body in WORKSPACE_ENDPOINTS[3:]:
            response = await client.request(
                method, _url(template, anas["id"], bob.id), headers=ana.headers, json=body
            )
            assert response.status_code == 404, f"{method} {template}"
            assert response.json()["error"]["code"] == "NOT_FOUND"

    async def test_a_nonexistent_user_id_is_just_not_found(self, client: AsyncClient) -> None:
        ana = await make_user(client, "ana@example.com")
        workspace = await make_workspace(client, ana)
        response = await client.delete(
            f"{API}/workspaces/{workspace['id']}/members/{MISSING_USER}", headers=ana.headers
        )
        assert response.status_code == 404
