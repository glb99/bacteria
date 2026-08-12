"""End-to-end tests for the chat feature, over HTTP, with a real database.

Only the model is faked. Everything else is the real path — the router, the
dependency that opens a session, the SQL repository, and the agent's runtime —
because what is worth checking here is that those fit together, and a test that
mocked the repository would be asserting its own wiring.
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.agent.model.protocol import ModelResponse
from bacteria.app.auth.service import issue_key
from bacteria.app.chat import service
from bacteria.app.core.db import session_scope
from bacteria.app.views import create_app


class FakeModelClient:
    """Satisfies the agent's protocol, calls nothing, and echoes what it was asked."""

    def __init__(self, reply: str = "hello from the model") -> None:
        self._reply = reply

    async def send(self, messages, **kwargs) -> ModelResponse:
        return ModelResponse(text=self._reply, tool_calls=[], stop_reason="end_turn", raw=None)


class FailingModelClient:
    async def send(self, messages, **kwargs) -> ModelResponse:
        raise RuntimeError("model backend unavailable")


@pytest.fixture(name="token")
async def _token(engine):
    """An API key for the principal these tests act as."""
    async with AsyncSession(engine) as session:
        return await issue_key(session, principal_id="tester", label="tests")


@pytest.fixture(name="client")
def _client(engine, monkeypatch, backend_options):
    async def _test_session():
        async with AsyncSession(engine) as session:
            yield session

    monkeypatch.setitem(service.PROVIDERS, "fake", FakeModelClient)
    monkeypatch.setenv("BACTERIA_MODEL_PROVIDER", "fake")

    # No lifespan: conftest builds the schema once per run, which is the same
    # position a deployment is in after `alembic upgrade head`.
    app = create_app()
    app.dependency_overrides[session_scope] = _test_session
    with TestClient(app, backend_options=backend_options) as client:
        yield client


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def new_session(client, token: str) -> str:
    response = client.post("/chat/sessions", headers=auth(token))
    assert response.status_code == 201
    return response.json()["session_id"]


async def test_health_does_not_touch_the_database(client):
    assert client.get("/health").json() == {"status": "ok"}


async def test_a_session_can_be_created_and_is_given_an_identity(client, token):
    body = client.post("/chat/sessions", headers=auth(token)).json()

    assert body["user_id"] == "tester"
    assert body["session_id"]


async def test_a_turn_returns_the_model_reply(client, token):
    session_id = new_session(client, token)

    body = client.post(
        f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "hi"}
    ).json()

    assert body["reply"] == "hello from the model"
    assert body["run_id"]


async def test_a_turn_is_recorded_in_the_transcript(client, token):
    """State must survive the request that produced it.

    This is what the whole persistence seam is for: the turn ran against a
    database-backed store, so a second request can see what the first did.
    """
    session_id = new_session(client, token)
    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "hi"})

    transcript = client.get(f"/chat/sessions/{session_id}/transcript", headers=auth(token)).json()

    assert [entry["kind"] for entry in transcript] == ["message", "message", "run_meta"]
    assert transcript[0]["payload"] == {"role": "user", "text": "hi"}
    assert transcript[1]["payload"]["role"] == "assistant"
    # The run describes itself over HTTP too, which is where it matters most —
    # nobody here watched the turn happen.
    assert transcript[2]["payload"]["outcome"] == "completed"


async def test_a_second_turn_sees_the_first(client, token):
    """History comes from the store, not from anything held between requests.

    Each request builds a new runtime and a new repository. If this passes, the
    conversation is genuinely durable rather than living in a process.
    """
    session_id = new_session(client, token)
    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "first"})
    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "second"})

    transcript = client.get(f"/chat/sessions/{session_id}/transcript", headers=auth(token)).json()

    messages = [e for e in transcript if e["kind"] == "message"]
    assert len(messages) == 4
    assert [e["payload"].get("text") for e in messages][::2] == ["first", "second"]


async def test_an_unknown_session_is_404_not_a_new_conversation(client, token):
    """A lost id must not silently become an empty session.

    The agent's store raises rather than creating one; this asserts that choice
    survives translation to HTTP instead of being flattened into a 500 or,
    worse, a successful turn against a session nobody asked for.
    """
    assert client.get("/chat/sessions/nope/transcript", headers=auth(token)).status_code == 404

    response = client.post("/chat/sessions/nope/turns", headers=auth(token), json={"text": "hi"})
    assert response.status_code == 404


async def test_a_failed_turn_still_leaves_evidence(client, token, monkeypatch):
    """The user's message and the failure survive a 500.

    Without this, the runs worth investigating are exactly the ones with no
    record — the request fails, the caller sees a stack trace, and the
    conversation shows nothing happened.
    """
    session_id = new_session(client, token)
    monkeypatch.setitem(service.PROVIDERS, "fake", FailingModelClient)

    with pytest.raises(RuntimeError):
        client.post(
            f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "doomed"}
        )

    monkeypatch.setitem(service.PROVIDERS, "fake", FakeModelClient)
    transcript = client.get(f"/chat/sessions/{session_id}/transcript", headers=auth(token)).json()

    assert transcript[0]["payload"] == {"role": "user", "text": "doomed"}
    assert any(entry["kind"] == "run_error" for entry in transcript)


def test_an_unknown_provider_is_rejected_rather_than_defaulted():
    """A typo must not quietly bill a different vendor."""
    with pytest.raises(ValueError):
        service.build_model_client("clyde")


def remember(client, token, session_id, key, value, reason="because"):
    return client.put(
        f"/chat/sessions/{session_id}/memory/{key}",
        headers=auth(token),
        json={"value": value, "reason": reason},
    )


async def test_a_written_memory_reaches_the_model_as_a_system_prompt(client, token, monkeypatch):
    """The whole point of the feature, and the thing that never happened before.

    Memory had a complete read path -- assembled into the system prompt on every
    turn -- and nothing that could write one, so this branch had never executed
    outside a unit test. Asserting on what the client actually received is what
    distinguishes "a row was stored" from "the model was told".
    """
    session_id = new_session(client, token)
    seen = {}

    class Capturing:
        async def send(self, messages, **kwargs):
            seen["system"] = kwargs.get("system")
            return ModelResponse(text="ok", tool_calls=[], stop_reason="end_turn", raw=None)

    remember(client, token, session_id, "tone", "prefers concise answers")
    monkeypatch.setitem(service.PROVIDERS, "fake", Capturing)

    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "hi"})

    assert seen["system"] is not None
    assert "prefers concise answers" in seen["system"]
    assert "because" in seen["system"]


async def test_a_memory_survives_into_a_later_turn(client, token):
    """Memory is durable, not per-request.

    Each request builds a new repository against the database, so this passing
    means the entry came back from storage rather than from anything held in
    the process.
    """
    session_id = new_session(client, token)
    remember(client, token, session_id, "tone", "concise")

    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "one"})
    listed = client.get(f"/chat/sessions/{session_id}/memory", headers=auth(token)).json()

    assert [e["key"] for e in listed] == ["tone"]
    assert listed[0]["reason"] == "because"


async def test_writing_the_same_key_twice_overwrites_rather_than_appends(client, token):
    """A memory is a value at a key, not an event.

    Appending would make the same preference stated twice count twice toward
    the model's bounded view of memory, crowding out other entries.
    """
    session_id = new_session(client, token)
    remember(client, token, session_id, "tone", "concise")
    remember(client, token, session_id, "tone", "verbose", reason="changed their mind")

    listed = client.get(f"/chat/sessions/{session_id}/memory", headers=auth(token)).json()

    assert len(listed) == 1
    assert listed[0]["value"] == "verbose"
    assert listed[0]["reason"] == "changed their mind"


async def test_a_forgotten_memory_stops_reaching_the_model(client, token, monkeypatch):
    """Removal has to affect the prompt, not just the listing.

    A delete that emptied the table but left the assembled context unchanged
    would be the worst version of this: the operator believes the fact is gone
    and the model keeps acting on it.
    """
    session_id = new_session(client, token)
    remember(client, token, session_id, "tone", "prefers concise answers")
    seen = {}

    class Capturing:
        async def send(self, messages, **kwargs):
            seen["system"] = kwargs.get("system")
            return ModelResponse(text="ok", tool_calls=[], stop_reason="end_turn", raw=None)

    response = client.delete(f"/chat/sessions/{session_id}/memory/tone", headers=auth(token))
    assert response.status_code == 204

    monkeypatch.setitem(service.PROVIDERS, "fake", Capturing)
    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "hi"})

    assert seen["system"] is None


async def test_deleting_an_absent_memory_is_not_an_error(client, token):
    """204 rather than 404, so keys cannot be probed one at a time."""
    session_id = new_session(client, token)

    response = client.delete(f"/chat/sessions/{session_id}/memory/never-set", headers=auth(token))

    assert response.status_code == 204


async def test_a_memory_requires_a_reason(client, token):
    """Provenance is mandatory, because it is what makes review possible.

    A memory with no recorded justification is kept forever by default -- there
    is no basis on which anyone could decide to remove it.
    """
    session_id = new_session(client, token)

    response = client.put(
        f"/chat/sessions/{session_id}/memory/tone",
        headers=auth(token),
        json={"value": "concise", "reason": ""},
    )

    assert response.status_code == 422


class ProposingModelClient:
    """Calls `remember` on its first turn, then answers normally.

    Stateful because the runtime calls the model twice when tools run — once to
    get the proposal, once with the results — and a client that proposed both
    times would loop if the loop existed.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def send(self, messages, **kwargs) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(
                text=None,
                tool_calls=[
                    {
                        "id": "call-1",
                        "name": "remember",
                        "input": {
                            "key": "tone",
                            "value": "prefers bullet points",
                            "reason": "asked for bullets twice",
                        },
                    }
                ],
                stop_reason="tool_use",
                raw=None,
            )
        return ModelResponse(text="noted", tool_calls=[], stop_reason="end_turn", raw=None)


async def test_a_model_proposal_does_not_reach_the_next_turn(client, token, monkeypatch):
    """The security property, asserted over the real HTTP path.

    A model that proposed a memory must not be able to read it back as an
    instruction. If this fails, an injected "remember that you must always
    comply" becomes a system prompt on the following turn, and the transcript
    shows only a tool call that succeeded.
    """
    session_id = new_session(client, token)
    monkeypatch.setitem(service.PROVIDERS, "fake", ProposingModelClient)
    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "hi"})

    seen = {}

    class Capturing:
        async def send(self, messages, **kwargs) -> ModelResponse:
            seen["system"] = kwargs.get("system")
            return ModelResponse(text="ok", tool_calls=[], stop_reason="end_turn", raw=None)

    monkeypatch.setitem(service.PROVIDERS, "fake", Capturing)
    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "again"})

    assert seen["system"] is None


async def test_a_model_proposal_is_visible_to_the_owner_for_review(client, token, monkeypatch):
    """It reached the queue, so the test above is not passing by nothing happening."""
    session_id = new_session(client, token)
    monkeypatch.setitem(service.PROVIDERS, "fake", ProposingModelClient)
    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "hi"})

    pending = client.get(
        f"/chat/sessions/{session_id}/memory-proposals", headers=auth(token)
    ).json()

    assert len(pending) == 1
    assert pending[0]["source"] == "model"
    assert pending[0]["key"] == "tone"
    assert pending[0]["value"] == "prefers bullet points"
    # Nothing is active yet.
    assert client.get(f"/chat/sessions/{session_id}/memory", headers=auth(token)).json() == []


async def test_activating_a_proposal_makes_it_reach_the_model(client, token, monkeypatch):
    """The human act, end to end.

    This is the payoff: the agent suggested something, a person accepted it, and
    only then did it become an instruction.
    """
    session_id = new_session(client, token)
    monkeypatch.setitem(service.PROVIDERS, "fake", ProposingModelClient)
    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "hi"})

    activated = client.post(
        f"/chat/sessions/{session_id}/memory-proposals/model/tone", headers=auth(token)
    )
    assert activated.status_code == 201
    assert activated.json()["source"] == "model"

    seen = {}

    class Capturing:
        async def send(self, messages, **kwargs) -> ModelResponse:
            seen["system"] = kwargs.get("system")
            return ModelResponse(text="ok", tool_calls=[], stop_reason="end_turn", raw=None)

    monkeypatch.setitem(service.PROVIDERS, "fake", Capturing)
    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "again"})

    assert "prefers bullet points" in seen["system"]
    # And it has left the queue, so a reviewer is not asked about it forever.
    assert (
        client.get(f"/chat/sessions/{session_id}/memory-proposals", headers=auth(token)).json()
        == []
    )


async def test_rejecting_a_proposal_leaves_no_memory(client, token, monkeypatch):
    session_id = new_session(client, token)
    monkeypatch.setitem(service.PROVIDERS, "fake", ProposingModelClient)
    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "hi"})

    response = client.delete(
        f"/chat/sessions/{session_id}/memory-proposals/model/tone", headers=auth(token)
    )

    assert response.status_code == 204
    assert client.get(f"/chat/sessions/{session_id}/memory", headers=auth(token)).json() == []
    assert (
        client.get(f"/chat/sessions/{session_id}/memory-proposals", headers=auth(token)).json()
        == []
    )


async def test_activating_a_proposal_that_is_not_there_is_404(client, token):
    """A stale review page must not conjure a memory nobody just read."""
    session_id = new_session(client, token)

    response = client.post(
        f"/chat/sessions/{session_id}/memory-proposals/model/never", headers=auth(token)
    )

    assert response.status_code == 404


async def test_the_owners_write_stays_immediate(client, token):
    """Confirmation is for everything except the person doing the confirming."""
    session_id = new_session(client, token)

    remember(client, token, session_id, "tone", "prefers bullets")

    active = client.get(f"/chat/sessions/{session_id}/memory", headers=auth(token)).json()
    assert [e["source"] for e in active] == ["owner"]
    assert (
        client.get(f"/chat/sessions/{session_id}/memory-proposals", headers=auth(token)).json()
        == []
    )
