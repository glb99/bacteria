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

from bacteria.app.architecture.decisions import decide, ontology_of
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
        response = judge(client, token, project, "bacteria.app.personal", "feature", "agreed")

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
        judge(client, token, project, "bacteria.app.personal", "feature", "disagreed")

        body = client.get(f"/architecture/projects/{project}/model", headers=auth(token)).json()
        chat = next(p for p in body["proposals"] if p["subject"] == "bacteria.app.personal")

        assert chat["verdict"] == "disagreed"

    async def test_a_judged_proposal_still_appears(self, client, token, project) -> None:
        """Hiding what was rejected would hide that anything was ever rejected."""
        judge(client, token, project, "bacteria.app.personal", "feature", "disagreed")

        body = client.get(f"/architecture/projects/{project}/model", headers=auth(token)).json()

        assert any(p["subject"] == "bacteria.app.personal" for p in body["proposals"])

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
        judge(client, token, project, "bacteria.app.personal", "feature", "agreed")
        judge(client, token, project, "bacteria.app.personal", "feature", "disagreed")

        body = client.get(f"/architecture/projects/{project}/model", headers=auth(token)).json()
        chat = next(p for p in body["proposals"] if p["subject"] == "bacteria.app.personal")

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
        principal. If the partition leaked, *"bacteria.app.personal is a feature"*
        would show up in somebody's personal graph — and, worse, could be
        surfaced to a model as something they said about their life.
        """
        judge(client, token, project, "bacteria.app.personal", "feature", "agreed")

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
        judge(client, token, project, "bacteria.app.personal", "feature", "agreed")

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

        response = judge(client, other, project, "bacteria.app.personal", "feature", "agreed")

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
        judge(client, token, project, "bacteria.app.personal", "feature", "agreed")
        judge(client, token, project, "bacteria.app.personal", "feature", "disagreed")

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
        judge(client, token, project, "bacteria.app.personal", "feature", "agreed")
        async with AsyncSession(engine) as session:
            standing = await architecture_log(session, project).current("tester")
        made_at = standing[0].recorded_at

        judge(client, token, project, "bacteria.app.personal", "feature", "disagreed")

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
        judge(client, token, project, "bacteria.app.personal", "feature", "agreed")
        async with AsyncSession(engine) as session:
            first = await architecture_log(session, project).current("tester")

        judge(client, token, project, "bacteria.app.personal", "feature", "agreed")

        async with AsyncSession(engine) as session:
            standing = await architecture_log(session, project).current("tester")

        assert len(standing) == 1
        assert standing[0].recorded_at == first[0].recorded_at


def project_row(project: str) -> Project:
    """The stored project as a dataclass, for calls that bypass the route.

    Needed because the only way to create an orphan is to record a judgment
    about a package the parse no longer produces -- and the route refuses
    exactly that, which is correct and makes the state unreachable through it.
    """
    return Project(
        project_id=project,
        principal_id="tester",
        name="",
        location=str(REPO),
        test_command=None,
        added_at=datetime.now(timezone.utc),
    )


async def judged_long_ago(engine, project: str, subject: str, stated_by: str) -> None:
    """A standing judgment about a package that has since gone."""
    async with AsyncSession(engine) as session:
        await decide(
            architecture_log(session, project),
            project=project_row(project),
            subject=subject,
            claim="feature",
            verdict="agreed",
            stated_by=stated_by,
            now=datetime.now(timezone.utc),
        )
        await session.commit()


def rename(client, token, project, was, now_called):
    return client.post(
        f"/architecture/projects/{project}/renames",
        headers=auth(token),
        json={"was": was, "now_called": now_called},
    )


class TestARenamedPackage:
    """What happens to a judgment when the thing it was about changes its name.

    Unique to a derived domain, and the gap dialogue 13 listed in scope and
    nobody built until a refactor produced a live instance of it: renaming
    ``chat`` to ``personal`` left a standing, true, invisible judgment behind.
    """

    async def test_a_judgment_about_a_vanished_package_is_reported_as_an_orphan(
        self, client, token, project, engine
    ) -> None:
        """Standing, true, and joined to no proposal.

        Before ``orphans`` existed this decision was invisible on every surface
        while remaining in the log, which is the worst of the three states it
        could be in: a person cannot act on a record they cannot see, and the
        graph must not forget it on their behalf.
        """
        await judged_long_ago(engine, project, "bacteria.app.chat", "tester")

        body = client.get(f"/architecture/projects/{project}/model", headers=auth(token)).json()

        assert [o["subject"] for o in body["orphans"]] == ["bacteria.app.chat"]
        assert body["orphans"][0]["verdict"] == "agreed"

    async def test_stating_the_rename_moves_the_judgment_and_empties_the_orphans(
        self, client, token, project, engine
    ) -> None:
        """The whole loop, and the reason it is not an ``UPDATE``.

        ``bacteria.app.chat`` was judged on a day that package existed.
        Rewriting the row to say ``personal`` would claim somebody judged a
        package that did not yet exist -- the manufactured history the log
        refuses -- so the row keeps its subject and the *read* resolves it.

        The author travels, which is the difference between this and asking the
        person to judge the same package again under its new name.
        """
        await judged_long_ago(engine, project, "bacteria.app.chat", "somebody-else")

        stated = rename(client, token, project, "bacteria.app.chat", "bacteria.app.personal")

        assert stated.status_code == 200
        body = client.get(f"/architecture/projects/{project}/model", headers=auth(token)).json()
        personal = next(p for p in body["proposals"] if p["subject"] == "bacteria.app.personal")

        assert body["orphans"] == []
        assert personal["verdict"] == "agreed"
        assert personal["stated_by"] == "somebody-else"

    async def test_the_old_row_keeps_its_own_subject(self, client, token, project, engine) -> None:
        """Resolved at read time, never rewritten.

        Checked at the log rather than through the response, because the whole
        argument for doing it this way is invisible from outside: both spellings
        produce the same screen, and only the rows say whether a date and an
        author were preserved or invented.
        """
        await judged_long_ago(engine, project, "bacteria.app.chat", "somebody-else")
        rename(client, token, project, "bacteria.app.chat", "bacteria.app.personal")

        async with AsyncSession(engine) as session:
            standing = await architecture_log(session, project).current("tester")

        judgments = [c for c in standing if c.rel in ("is_a", "is_not_a")]
        assert [c.attrs["subject"] for c in judgments] == ["bacteria.app.chat"]

    async def test_renaming_to_a_package_that_is_not_here_is_refused(
        self, client, token, project
    ) -> None:
        """Otherwise the judgment moves to a subject nothing can display.

        That failure is silent and worse than the orphan it was meant to fix:
        the decision leaves a name a person recognises and arrives at one that
        appears nowhere at all.
        """
        response = rename(client, token, project, "bacteria.app.chat", "not.a.package")

        assert response.status_code == 409
        assert "no package called" in response.json()["detail"]

    async def test_renaming_something_still_here_is_refused(self, client, token, project) -> None:
        """A rename between two live packages says one codebase holds it twice.

        The plausible typo -- two real names, both recognised, in the wrong
        order -- and it would carry judgments backwards into a subject the parse
        still produces.
        """
        response = rename(client, token, project, "bacteria.app.graph", "bacteria.app.architecture")

        assert response.status_code == 409
        assert "still here" in response.json()["detail"]

    async def test_a_judgment_about_the_current_name_wins(
        self, client, token, project, engine
    ) -> None:
        """Two statements about one package, and one is about it as it now is.

        A carried judgment is at best what somebody thought before the rename;
        one made about the current name was made with the package in front of
        them.
        """
        await judged_long_ago(engine, project, "bacteria.app.chat", "somebody-else")
        rename(client, token, project, "bacteria.app.chat", "bacteria.app.personal")

        judge(client, token, project, "bacteria.app.personal", "feature", "disagreed")

        body = client.get(f"/architecture/projects/{project}/model", headers=auth(token)).json()
        personal = next(p for p in body["proposals"] if p["subject"] == "bacteria.app.personal")

        # Asserted together, because the verdict alone passes for the wrong
        # reason: with the rename unresolved the carried judgment never reaches
        # the response at all, and the direct one wins by being the only one
        # there. An empty `orphans` is what says the carried judgment arrived
        # and then lost on merit.
        assert body["orphans"] == []
        assert personal["verdict"] == "disagreed"
        assert personal["stated_by"] == "tester"

    async def test_saying_the_same_rename_twice_keeps_the_first_one(
        self, client, token, project, engine
    ) -> None:
        """Restating is not a second rename.

        The date is the only fact the row holds that cannot be recovered from
        the tree, so re-stating must not move it -- the same rule ``decide``
        applies to a restated judgment, in the same file, for the same reason.
        """
        rename(client, token, project, "bacteria.app.chat", "bacteria.app.personal")
        rename(client, token, project, "bacteria.app.chat", "bacteria.app.personal")

        async with AsyncSession(engine) as session:
            standing = await architecture_log(session, project).current("tester")

        assert len([c for c in standing if c.rel == "same_as"]) == 1
