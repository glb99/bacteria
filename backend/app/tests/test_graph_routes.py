"""Reading the graph over HTTP, and never reading anyone else's.

These routes take no id of anything: each asks for *the caller's own* graph, so
ownership is a filter rather than a check. That is the safer shape and the more
dangerous failure — `chat/views.py` puts it exactly right, that a broken check
refuses a legitimate caller while a broken filter hands over everyone else's
data. So the filter is asserted here rather than trusted.

The other thing worth a test is the wire format of a temporal bound. Three
states share one column and a JSON `null` cannot carry three, so `ends` is a
rendered string; a client that could not tell "still true" from "nobody knows"
would have no way to render a contradiction differently from missing dates.

Real Postgres. Start it with `just db-up`.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.auth.service import issue_key
from bacteria.app.core.db import session_scope
from bacteria.app.graph.conclusions import Conclusion
from bacteria.app.graph.log import Assertion
from bacteria.app.graph.repository import SqlGraphRepository
from bacteria.app.graph.service import refer_to
from bacteria.app.graph.temporal import OPEN_ENDED, Interval
from bacteria.app.views import create_app

NOW = datetime(2026, 5, 4, tzinfo=timezone.utc)
FEBRUARY = datetime(2026, 2, 15, tzinfo=timezone.utc)


@pytest.fixture(name="client")
def _client(engine, backend_options):
    async def _test_session():
        async with AsyncSession(engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[session_scope] = _test_session
    with TestClient(app, backend_options=backend_options) as client:
        yield client


@pytest.fixture(name="issue")
def _issue(engine):
    async def _make(principal_id: str) -> str:
        async with AsyncSession(engine) as session:
            return await issue_key(session, principal_id=principal_id, label=principal_id)

    return _make


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed(engine, user_id: str, *, holder: str = "diane", end=OPEN_ENDED) -> None:
    """One organization, one person, one claim relating them.

    Nodes come from ``refer_to`` rather than ``mint_node``, which is what the
    extractor does and is load-bearing for the conflict case: ``mint_node``
    always allocates, so seeding two claims about "Acme" that way produces two
    *different* Acme nodes, the functional constraint groups by subject, and the
    contradiction the test is looking for cannot exist. Found by writing it the
    other way first.
    """
    async with AsyncSession(engine) as session:
        repo = SqlGraphRepository(session)
        org = await refer_to(repo, user_id, "organization", "Acme", now=NOW)
        person = await refer_to(repo, user_id, "person", holder, now=NOW)
        await repo.record(
            [
                Assertion(
                    assertion_id=f"a-{user_id}-{holder}",
                    user_id=user_id,
                    src=org.node_id,
                    dst=person.node_id,
                    rel="cto",
                    valid=Interval(None, end),
                    recorded_at=NOW,
                    attrs={"reason": "said so in conversation"},
                )
            ]
        )
        await session.commit()


async def test_the_graph_comes_back_with_its_nodes_and_claims(client, issue, engine):
    """The ordinary read: what this person's memory currently holds."""
    token = await issue("acme")
    await _seed(engine, "acme")

    body = client.get("/graph", headers=auth(token)).json()

    assert {n["label"] for n in body["nodes"]} == {"Acme", "diane"}
    assert [a["rel"] for a in body["assertions"]] == ["cto"]
    assert body["assertions"][0]["reason"] == "said so in conversation"


async def test_a_bound_says_which_of_its_three_states_it_is_in(client, issue, engine):
    """`open`, `unknown` and a date must be distinguishable on the wire.

    A nullable timestamp would make the first two identical, and a client would
    have to know that the open sentinel is a particular instant in the year 9999
    to tell "still true" from "nobody recorded when it stopped" — knowledge an
    API has no business requiring.
    """
    token = await issue("acme")
    await _seed(engine, "acme", holder="diane", end=OPEN_ENDED)
    await _seed(engine, "acme", holder="bob", end=None)
    await _seed(engine, "acme", holder="carol", end=FEBRUARY)

    body = client.get("/graph", headers=auth(token)).json()

    assert {a["ends"] for a in body["assertions"]} == {
        "open",
        "unknown",
        FEBRUARY.isoformat(),
    }


async def test_a_contradiction_is_reported_with_the_rule_that_found_it(client, issue, engine):
    """Two current claims collide, and the rule travels with the collision.

    The sentence is there because a constraint is a hypothesis about the user's
    world rather than something the system is entitled to enforce — and a person
    cannot contest a rule they cannot read.
    """
    token = await issue("acme")
    await _seed(engine, "acme", holder="diane")
    await _seed(engine, "acme", holder="bob")

    body = client.get("/graph", headers=auth(token)).json()

    assert [c["state"] for c in body["conflicts"]] == ["conflict"]
    assert body["conflicts"][0]["sentence"] == "An organization has one CTO at a time."


async def test_one_principal_never_sees_anothers_graph(client, issue, engine):
    """The filter, asserted rather than trusted.

    No route here takes an id, so there is no check to get wrong — which means
    the only way this fails is a missing owner predicate in a query, and that
    failure hands over someone else's memory rather than refusing them their own.
    """
    owner, intruder = await issue("acme"), await issue("rival")
    await _seed(engine, "acme")

    theirs = client.get("/graph", headers=auth(intruder)).json()

    assert theirs["nodes"] == []
    assert theirs["assertions"] == []
    assert client.get("/graph", headers=auth(owner)).json()["assertions"] != []


async def test_the_graph_needs_a_credential(client):
    """Unauthenticated is refused, not answered with an empty graph.

    An empty body would be indistinguishable from a new user's real graph, so a
    broken dependency would look like a working route.
    """
    assert client.get("/graph").status_code == 401


async def test_conclusions_come_back_with_their_evidence(client, issue, engine):
    """A belief a person cannot trace is one they can only take on faith."""
    token = await issue("acme")
    await _seed(engine, "acme")

    async with AsyncSession(engine) as session:
        await SqlGraphRepository(session).record_conclusion(
            Conclusion(
                conclusion_id="c1",
                user_id="acme",
                statement="Diane is the decision-maker",
                evidence=("a-acme-diane",),
                confidence=0.72,
                derived_by="llm-judgment",
                recorded_at=NOW,
            )
        )
        await session.commit()

    body = client.get("/graph/conclusions", headers=auth(token)).json()

    assert [c["statement"] for c in body] == ["Diane is the decision-maker"]
    assert body[0]["evidence"] == ["a-acme-diane"]


async def test_one_principal_never_sees_anothers_conclusions(client, issue, engine):
    """The same filter, on the route that carries the reasoning."""
    _, intruder = await issue("acme"), await issue("rival")
    await _seed(engine, "acme")

    assert client.get("/graph/conclusions", headers=auth(intruder)).json() == []
