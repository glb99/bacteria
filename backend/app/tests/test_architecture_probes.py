"""Asking the world how a codebase is doing.

The first world-action in this feature, so most of what is checked is the line
it sits on: that a reading never becomes a belief, that *not checked* is not
*fine*, and that no command ever arrives from a request.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.architecture.models import Project
from bacteria.app.architecture.probes import describe, run_tests
from bacteria.app.auth.service import issue_key
from bacteria.app.core.db import session_scope
from bacteria.app.graph.repository import SqlGraphRepository
from bacteria.app.views import create_app

REPO = Path(__file__).resolve().parents[3]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _project(tmp_path: Path, command: str | None) -> Project:
    from datetime import datetime, timezone

    return Project(
        project_id="p1",
        principal_id="tester",
        name="probe",
        location=str(tmp_path),
        test_command=command,
        added_at=datetime.now(timezone.utc),
    )


@pytest.fixture(name="token")
async def _token(engine):
    async with AsyncSession(engine) as session:
        return await issue_key(session, principal_id="tester", label="tests")


@pytest.fixture(name="client")
def _client(engine, backend_options):
    async def _test_session():
        async with AsyncSession(engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[session_scope] = _test_session
    with TestClient(app, backend_options=backend_options) as client:
        yield client


class TestRunningTests:
    async def test_a_passing_command_reads_ok(self, tmp_path: Path) -> None:
        """The ordinary case, run for real rather than mocked.

        A mocked subprocess would assert that this module calls a function, not
        that a command runs in the right directory and its exit status is read —
        which is the entire content of the probe.
        """
        reading = await run_tests(_project(tmp_path, f'"{sys.executable}" -c "pass"'))

        assert reading.state == "ok"
        assert reading.ok

    async def test_a_failing_command_reads_failing_and_keeps_the_tail(self, tmp_path: Path) -> None:
        """A failure has to carry what failed, or nobody can act on it.

        The tail rather than the head: a suite says what broke at the end, and
        the first characters of a test run are its collection log.

        The script is a file rather than a ``-c`` string because the command
        runs through the platform shell, and quoting a program inline is written
        one way for ``sh`` and another for ``cmd``. The first version of this
        test asserted exit status 3 and got 1 — a syntax error from its own
        quoting, reported as a failing suite, which is precisely the confusion
        this probe would cause for a real project if it were spelled that way.
        """
        script = tmp_path / "boom.py"
        script.write_text(
            """
import sys

print("the thing that broke")
sys.exit(3)
""",
            encoding="utf-8",
        )
        command = f'"{sys.executable}" "{script}"'

        reading = await run_tests(_project(tmp_path, command))

        assert reading.state == "failing"
        assert "3" in reading.detail
        assert "the thing that broke" in reading.output

    async def test_a_project_with_no_command_is_unavailable_not_ok(self, tmp_path: Path) -> None:
        """The state this probe exists to keep distinct.

        A project that never said how to check itself has not been checked.
        Reporting that as passing is a green tick for a suite nobody ran, which
        is the failure this whole feature argues against.
        """
        reading = await run_tests(_project(tmp_path, None))

        assert reading.state == "unavailable"
        assert not reading.ok

    async def test_a_missing_checkout_is_unavailable(self, tmp_path: Path) -> None:
        """The world moved under a stored path. Nothing is broken; nothing is known."""
        gone = _project(tmp_path / "not-here", "echo hello")

        reading = await run_tests(gone)

        assert reading.state == "unavailable"

    def test_never_checked_is_its_own_sentence(self) -> None:
        """``None`` has to be legible as a state rather than as an empty string."""
        assert describe(None) == "not checked"


class TestTheRoute:
    async def test_a_reading_is_returned_and_never_written(
        self, client, token, tmp_path, engine
    ) -> None:
        """A world-action changes the world, never the model.

        The tests were green four minutes ago and may be red now. A fact with a
        shelf life of one commit would make every replay of a past run wrong in
        a new way, so the answer is shown and forgotten.
        """
        created = client.post(
            "/architecture/projects",
            headers=auth(token),
            json={
                "location": str(REPO),
                "test_command": f'"{sys.executable}" -c "pass"',
            },
        )
        project_id = created.json()["project_id"]

        response = client.post(
            f"/architecture/projects/{project_id}/probes/tests", headers=auth(token)
        )

        assert response.status_code == 200
        assert response.json()["state"] == "ok"

        async with AsyncSession(engine) as db:
            for ontology in (None, f"architecture:{project_id}"):
                claims = await SqlGraphRepository(db, ontology=ontology).current("tester")
                assert claims == []

    async def test_the_route_takes_no_command(self, client, token) -> None:
        """The whole security posture of this probe, asserted rather than trusted.

        A body naming a command would be remote code execution with extra steps.
        The command belongs to the project row, set by an operator who already
        has a shell on this machine.
        """
        created = client.post(
            "/architecture/projects", headers=auth(token), json={"location": str(REPO)}
        )
        project_id = created.json()["project_id"]

        response = client.post(
            f"/architecture/projects/{project_id}/probes/tests",
            headers=auth(token),
            json={"command": "echo pwned"},
        )

        # Accepted and ignored: the project has no command, so nothing ran.
        assert response.json()["state"] == "unavailable"

    async def test_adding_again_with_a_command_sets_it(self, client, token) -> None:
        """Saying it again *with new information* is not the same statement.

        Found against a real server rather than in a test: a project added
        before this probe existed could never be told how to check itself,
        because re-adding returned the existing row and dropped the command.
        The probe answered "no test command configured" forever.
        """
        first = client.post(
            "/architecture/projects", headers=auth(token), json={"location": str(REPO)}
        ).json()
        assert first["test_command"] is None

        again = client.post(
            "/architecture/projects",
            headers=auth(token),
            json={"location": str(REPO), "test_command": "echo hello"},
        ).json()

        assert again["project_id"] == first["project_id"]
        assert again["test_command"] == "echo hello"

    async def test_another_principals_project_cannot_be_probed(self, client, token, engine) -> None:
        """Running something is the last act that should answer to a stranger."""
        created = client.post(
            "/architecture/projects", headers=auth(token), json={"location": str(REPO)}
        )
        project_id = created.json()["project_id"]

        async with AsyncSession(engine) as session:
            other = await issue_key(session, principal_id="stranger", label="tests")

        response = client.post(
            f"/architecture/projects/{project_id}/probes/tests", headers=auth(other)
        )

        assert response.status_code == 404
