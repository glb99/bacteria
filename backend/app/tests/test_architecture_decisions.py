"""Agreeing and disagreeing with what a codebase suggests about itself.

The first thing this feature writes, and the first architecture rows to share a
table with somebody's personal memory. Most of what is checked here is that they
do **not** meet.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.architecture.decisions import ontology_of
from bacteria.app.architecture.models import Project
from bacteria.app.auth.service import issue_key
from bacteria.app.core.db import session_scope
from bacteria.app.graph.repository import SqlGraphRepository
from bacteria.app.views import create_app

REPO = Path(__file__).resolve().parents[3]


def architecture_log(session, project: str) -> SqlGraphRepository:
    """The graph as this project's model sees it.

    Scoped, because an unscoped repository reads the ``ontology IS NULL``
    partition — somebody's personal memory — and returns nothing at all here.
    Which is the isolation working: the first version of these tests looked
    like the rows had never been written.

    Through :func:`ontology_of` rather than an f-string, so a change to the
    partition's spelling fails at the import and not as three empty lists.
    """
    return SqlGraphRepository(
        session,
        ontology=ontology_of(
            Project(
                project_id=project,
                principal_id="tester",
                name="",
                location="",
                test_command=None,
                added_at=datetime.now(timezone.utc),
            )
        ),
    )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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


@pytest.fixture(name="project")
def _project(client, token):
    created = client.post(
        "/architecture/projects", headers=auth(token), json={"location": str(REPO)}
    )
    assert created.status_code == 201
    return created.json()["project_id"]


def judge(client, token, project, subject, claim, verdict):
    return client.post(
        f"/architecture/projects/{project}/classifications",
        headers=auth(token),
        json={"subject": subject, "claim": claim, "verdict": verdict},
    )


class TestJudging:
    async def test_agreeing_is_recorded_with_who_said_it(self, client, token, project) -> None:
        """A person's opinion is the only thing here that is not read off syntax.

        It carries their name because a shared architecture asks *who decided
        this* first, and a row written without an author can never be given one
        — inventing one afterwards is the false history the log forbids.
        """
        response = judge(client, token, project, "bacteria.app.chat", "feature", "agreed")

        assert response.status_code == 200
        assert response.json()["verdict"] == "agreed"
        assert response.json()["stated_by"] == "tester"

    async def test_disagreeing_is_recorded_rather_than_dropped(
        self, client, token, project
    ) -> None:
        """A rejection is a fact, not the absence of one.

        Dropped instead, the same regularity re-proposes the same claim forever
        and the queue becomes something people stop reading. It is also the
        number this surface exists to produce.
        """
        judge(client, token, project, "bacteria.app.chat", "feature", "disagreed")

        body = client.get(f"/architecture/projects/{project}/model", headers=auth(token)).json()
        chat = next(p for p in body["proposals"] if p["subject"] == "bacteria.app.chat")

        assert chat["verdict"] == "disagreed"

    async def test_a_judged_proposal_still_appears(self, client, token, project) -> None:
        """Hiding what was rejected would hide that anything was ever rejected."""
        judge(client, token, project, "bacteria.app.chat", "feature", "disagreed")

        body = client.get(f"/architecture/projects/{project}/model", headers=auth(token)).json()

        assert any(p["subject"] == "bacteria.app.chat" for p in body["proposals"])

    async def test_an_unjudged_proposal_has_no_verdict(self, client, token, project) -> None:
        """*Not yet judged* and *judged no* must never be the same state.

        A boolean would conflate them, and the second is the one worth counting.
        """
        body = client.get(f"/architecture/projects/{project}/model", headers=auth(token)).json()

        assert all(p["verdict"] is None for p in body["proposals"])

    async def test_changing_your_mind_replaces_the_verdict(self, client, token, project) -> None:
        """Two judgments at two times, not an edit.

        The old row closes and the new one opens, so *what did they think in
        March* stays answerable — which is the entire reason these live in a
        bi-temporal log rather than a settings table.
        """
        judge(client, token, project, "bacteria.app.chat", "feature", "agreed")
        judge(client, token, project, "bacteria.app.chat", "feature", "disagreed")

        body = client.get(f"/architecture/projects/{project}/model", headers=auth(token)).json()
        chat = next(p for p in body["proposals"] if p["subject"] == "bacteria.app.chat")

        assert chat["verdict"] == "disagreed"

    async def test_judging_something_no_longer_proposed_is_refused(
        self, client, token, project
    ) -> None:
        """The tree moves under these proposals.

        A judgment about a regularity that has since gone is a decision about a
        codebase that no longer exists, and storing it would leave a verdict
        attached to nothing anybody can see.
        """
        response = judge(client, token, project, "not.a.package", "feature", "agreed")

        assert response.status_code == 409


class TestIsolation:
    async def test_an_architecture_decision_is_not_in_the_memory_graph(
        self, client, token, project, engine
    ) -> None:
        """The property the whole ontology column exists for.

        These rows sit in the same table as a person's memory, keyed by the same
        principal. If the partition leaked, *"bacteria.app.chat is a feature"*
        would show up in somebody's personal graph — and, worse, could be
        surfaced to a model as something they said about their life.
        """
        judge(client, token, project, "bacteria.app.chat", "feature", "agreed")

        async with AsyncSession(engine) as db:
            memory = SqlGraphRepository(db)
            claims = await memory.current("tester")
            nodes = await memory.nodes("tester")

        assert [c for c in claims if c.rel in ("is_a", "is_not_a")] == []
        assert [n for n in nodes if n.kind in ("package", "kind", "word")] == []

    async def test_the_decision_is_in_its_own_ontology(
        self, client, token, project, engine
    ) -> None:
        """And it is genuinely stored, rather than merely absent from memory.

        Without this the test above passes for the wrong reason — a write that
        silently did nothing would also leave the memory graph clean.
        """
        judge(client, token, project, "bacteria.app.chat", "feature", "agreed")

        async with AsyncSession(engine) as db:
            arch = SqlGraphRepository(db, ontology=f"architecture:{project}")
            claims = await arch.current("tester")

        stated = [c for c in claims if c.rel == "is_a"]
        assert len(stated) == 1
        assert stated[0].origin == "stated"
        assert stated[0].stated_by == "tester"

    async def test_another_principal_cannot_judge_your_project(
        self, client, token, project, engine
    ) -> None:
        """Ownership is decided beside the resource, and answers 404."""
        async with AsyncSession(engine) as session:
            other = await issue_key(session, principal_id="stranger", label="tests")

        response = judge(client, other, project, "bacteria.app.chat", "feature", "agreed")

        assert response.status_code == 404


class TestWhatSurvivesAReversal:
    """The log, not the answer computed from it.

    ``test_changing_your_mind_replaces_the_verdict`` above asserts what the
    model endpoint reports, and it passed for the whole life of the bug: the
    route folds decisions into a dict keyed by ``(subject, claim)``, so a stale
    ``is_a`` standing beside a fresh ``is_not_a`` is silently overwritten by
    whichever row the database returned second. The reported verdict was right
    by luck. These go to the rows.
    """

    async def test_a_reversal_leaves_exactly_one_claim_standing(
        self, client, token, project, engine
    ) -> None:
        """Two current rows saying opposite things is not a history, it is a bug.

        ``decide`` handed :meth:`close` the row straight out of ``current``,
        whose ``recorded_until`` is ``None`` by definition — so closing it
        assigned ``None`` over ``None`` and the old judgment never left. Three
        packages in the author's own database ended up simultaneously agreed and
        disagreed.
        """
        judge(client, token, project, "bacteria.app.chat", "feature", "agreed")
        judge(client, token, project, "bacteria.app.chat", "feature", "disagreed")

        async with AsyncSession(engine) as session:
            standing = await architecture_log(session, project).current("tester")

        rulings = [c for c in standing if c.rel in ("is_a", "is_not_a")]
        assert [c.rel for c in rulings] == ["is_not_a"]

    async def test_what_they_thought_before_is_still_answerable(
        self, client, token, project, engine
    ) -> None:
        """Closed, never deleted — which is the point of a bi-temporal log.

        Asked as of the moment the first judgment was made, the graph must still
        say *agreed*. ``closed_by`` must say *superseded* rather than
        *retracted*: the person stated a different judgment in its place, which
        is not the same act as withdrawing one and saying nothing — and only
        that field records which happened.
        """
        judge(client, token, project, "bacteria.app.chat", "feature", "agreed")
        async with AsyncSession(engine) as session:
            standing = await architecture_log(session, project).current("tester")
        made_at = standing[0].recorded_at

        judge(client, token, project, "bacteria.app.chat", "feature", "disagreed")

        async with AsyncSession(engine) as session:
            then = await architecture_log(session, project).believed_at("tester", made_at)

        assert [c.rel for c in then] == ["is_a"]
        assert then[0].closed_by == "superseded"

    async def test_restating_the_same_verdict_closes_nothing(
        self, client, token, project, engine
    ) -> None:
        """Guarded because the fix runs one line below the early return.

        Saying the same thing twice is not a change of mind. Closing and
        reopening it would move the date the judgment was actually made, which
        is the one fact the row exists to carry.
        """
        judge(client, token, project, "bacteria.app.chat", "feature", "agreed")
        async with AsyncSession(engine) as session:
            first = await architecture_log(session, project).current("tester")

        judge(client, token, project, "bacteria.app.chat", "feature", "agreed")

        async with AsyncSession(engine) as session:
            standing = await architecture_log(session, project).current("tester")

        assert len(standing) == 1
        assert standing[0].recorded_at == first[0].recorded_at
