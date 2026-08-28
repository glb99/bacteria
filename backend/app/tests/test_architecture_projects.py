"""Pointing the service at a codebase, and reading the model of one.

Split from ``test_architecture.py`` deliberately: that file needs no database
because a parse needs none, and this one drives the routes against a real
Postgres. Keeping them together would make the pure tests look like they
depended on infrastructure they do not.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.architecture.layout import source_roots
from bacteria.app.auth.service import issue_key
from bacteria.app.core.db import session_scope
from bacteria.app.views import create_app

REPO = Path(__file__).resolve().parents[3]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _package(root: Path, dotted: str, body: str = "") -> None:
    path = root.joinpath(*dotted.split("."))
    path.mkdir(parents=True, exist_ok=True)
    (path / "__init__.py").write_text(body, encoding="utf-8")


@pytest.fixture(name="token")
async def _token(engine):
    async with AsyncSession(engine) as session:
        return await issue_key(session, principal_id="tester", label="tests")


@pytest.fixture(name="other_token")
async def _other_token(engine):
    async with AsyncSession(engine) as session:
        return await issue_key(session, principal_id="stranger", label="tests")


@pytest.fixture(name="client")
def _client(engine, backend_options):
    async def _test_session():
        async with AsyncSession(engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[session_scope] = _test_session
    with TestClient(app, backend_options=backend_options) as client:
        yield client


class TestLayout:
    def test_a_src_layout_root_is_the_src_directory(self, tmp_path: Path) -> None:
        """``src/pkg/`` makes ``src`` the root, not ``src/pkg``.

        The root decides every module's dotted name, so getting it one level
        wrong renames everything and silently drops every import that spelled
        the old name in full.
        """
        _package(tmp_path, "src.pkg")

        assert {p.name for p in source_roots(tmp_path)} == {"src"}

    def test_a_namespace_package_does_not_shorten_the_root(self, tmp_path: Path) -> None:
        """A PEP 420 directory between ``src`` and the package is kept.

        This is the real failure it was written for: this workspace's
        ``src/bacteria/`` has no ``__init__.py``, so climbing stopped at
        ``src/bacteria`` and 232 of 234 imports stopped resolving. The graph came
        back small and tidy rather than obviously broken.
        """
        _package(tmp_path, "src.bacteria.app")

        assert {p.name for p in source_roots(tmp_path)} == {"src"}

    def test_a_flat_repository_roots_at_the_top(self, tmp_path: Path) -> None:
        """With no ``src``, the root is the package's parent."""
        _package(tmp_path, "mypkg")

        assert set(source_roots(tmp_path)) == {tmp_path}

    def test_a_virtualenv_is_not_part_of_the_project(self, tmp_path: Path) -> None:
        """``.venv`` and friends are never descended into.

        A checkout with its environment inside holds thousands of installed
        modules, and including them makes every question about the codebase an
        answer about its dependencies.
        """
        _package(tmp_path, "mypkg")
        _package(tmp_path, ".venv.lib.site-packages.requests")

        assert set(source_roots(tmp_path)) == {tmp_path}

    def test_two_unrelated_trees_give_two_roots(self, tmp_path: Path) -> None:
        """A workspace of several packages is several roots sharing one namespace."""
        _package(tmp_path, "backend.app.src.ns.app")
        _package(tmp_path, "backend.agent.src.ns.agent")

        roots = source_roots(tmp_path)

        assert sorted(roots.values()) == ["backend/agent/src", "backend/app/src"]


class TestProjects:
    async def test_a_checkout_can_be_added_and_read(self, client, token) -> None:
        """The whole slice: point at a repository, get its model back.

        Driven against this repository because it is the only checkout certain
        to exist, and because a model of it is a fact anyone can verify by hand.
        """
        created = client.post(
            "/architecture/projects",
            headers=auth(token),
            json={"location": str(REPO), "name": "bacteria"},
        )
        assert created.status_code == 201
        project_id = created.json()["project_id"]

        model = client.get(f"/architecture/projects/{project_id}/model", headers=auth(token))

        assert model.status_code == 200
        body = model.json()
        assert sorted(body["roots"]) == ["backend/agent/src", "backend/app/src"]
        assert len(body["modules"]) > 50
        assert any(m["name"] == "bacteria.app.graph.service" for m in body["modules"])
        assert "graph_assertion" in body["tables"]

    async def test_every_boundary_is_reported_including_the_undecidable(
        self, client, token
    ) -> None:
        """A boundary no import can settle is a state, not an omission.

        A client shown only the boundaries that could be checked would render a
        clean bill of health over questions nothing asked.
        """
        created = client.post(
            "/architecture/projects", headers=auth(token), json={"location": str(REPO)}
        )
        project_id = created.json()["project_id"]

        body = client.get(f"/architecture/projects/{project_id}/model", headers=auth(token)).json()

        states = {b["state"] for b in body["boundaries"]}
        assert "undecidable" in states
        assert all(b["elsewhere"] for b in body["boundaries"] if b["state"] == "undecidable")

    async def test_deferred_imports_reach_the_client(self, client, token) -> None:
        """The client must be able to draw a deferral differently from a breach.

        Without the flag a consumer reports six layering violations on a
        codebase whose boundary is intact.
        """
        created = client.post(
            "/architecture/projects", headers=auth(token), json={"location": str(REPO)}
        )
        project_id = created.json()["project_id"]

        body = client.get(f"/architecture/projects/{project_id}/model", headers=auth(token)).json()

        assert any(i["deferred"] for i in body["imports"])
        assert any(not i["deferred"] for i in body["imports"])

    async def test_adding_the_same_location_twice_returns_the_same_project(
        self, client, token
    ) -> None:
        """Saying it again is not an error, and must not mint a second row.

        Two projects for one checkout would each accumulate their own stated
        boundaries, which is the split-identity failure in a smaller costume.
        """
        first = client.post(
            "/architecture/projects", headers=auth(token), json={"location": str(REPO)}
        )
        second = client.post(
            "/architecture/projects", headers=auth(token), json={"location": str(REPO)}
        )

        assert first.json()["project_id"] == second.json()["project_id"]
        assert len(client.get("/architecture/projects", headers=auth(token)).json()) == 1

    async def test_a_path_with_no_packages_is_refused(self, client, token, tmp_path) -> None:
        """An empty directory is a typo, answered as one rather than as a project.

        Accepted, it would sit in the list reporting zero modules and no
        boundaries, which reads as a codebase with nothing wrong in it.
        """
        response = client.post(
            "/architecture/projects", headers=auth(token), json={"location": str(tmp_path)}
        )

        assert response.status_code == 400
        assert "packages" in response.json()["detail"]

    async def test_a_missing_path_is_refused(self, client, token, tmp_path) -> None:
        """A path that does not exist is a bad request, never a server error."""
        response = client.post(
            "/architecture/projects",
            headers=auth(token),
            json={"location": str(tmp_path / "nowhere")},
        )

        assert response.status_code == 400

    async def test_another_principals_project_is_not_readable(
        self, client, token, other_token
    ) -> None:
        """Ownership is decided beside the resource, and answers 404 rather than 403.

        Telling a caller that an id exists but is not theirs hands a guesser a
        way to enumerate real ids, and no caller here needs the distinction.
        """
        created = client.post(
            "/architecture/projects", headers=auth(token), json={"location": str(REPO)}
        )
        project_id = created.json()["project_id"]

        assert (
            client.get(
                f"/architecture/projects/{project_id}/model", headers=auth(other_token)
            ).status_code
            == 404
        )
        assert client.get("/architecture/projects", headers=auth(other_token)).json() == []
