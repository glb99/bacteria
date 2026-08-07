"""End-to-end tests for the chat feature, over HTTP, with a real database.

Only the model is faked. Everything else is the real path — the router, the
dependency that opens a session, the SQL repository, and the agent's runtime —
because what is worth checking here is that those fit together, and a test that
mocked the repository would be asserting its own wiring.
"""

import pytest
from bacteria.model.protocol import ModelResponse
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from fastpaip.auth.service import issue_key
from fastpaip.chat import service
from fastpaip.core.db import session_scope
from fastpaip.views import create_app


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
    monkeypatch.setenv("FASTPAIP_MODEL_PROVIDER", "fake")

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

    transcript = client.get(
        f"/chat/sessions/{session_id}/transcript", headers=auth(token)
    ).json()

    assert [entry["kind"] for entry in transcript] == ["message", "message"]
    assert transcript[0]["payload"] == {"role": "user", "text": "hi"}
    assert transcript[1]["payload"]["role"] == "assistant"


async def test_a_second_turn_sees_the_first(client, token):
    """History comes from the store, not from anything held between requests.

    Each request builds a new runtime and a new repository. If this passes, the
    conversation is genuinely durable rather than living in a process.
    """
    session_id = new_session(client, token)
    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "first"})
    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "second"})

    transcript = client.get(
        f"/chat/sessions/{session_id}/transcript", headers=auth(token)
    ).json()

    assert len(transcript) == 4
    assert [e["payload"].get("text") for e in transcript][::2] == ["first", "second"]


async def test_an_unknown_session_is_404_not_a_new_conversation(client, token):
    """A lost id must not silently become an empty session.

    The agent's store raises rather than creating one; this asserts that choice
    survives translation to HTTP instead of being flattened into a 500 or,
    worse, a successful turn against a session nobody asked for.
    """
    assert client.get("/chat/sessions/nope/transcript", headers=auth(token)).status_code == 404

    response = client.post(
        "/chat/sessions/nope/turns", headers=auth(token), json={"text": "hi"}
    )
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
        client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "doomed"})

    monkeypatch.setitem(service.PROVIDERS, "fake", FakeModelClient)
    transcript = client.get(
        f"/chat/sessions/{session_id}/transcript", headers=auth(token)
    ).json()

    assert transcript[0]["payload"] == {"role": "user", "text": "doomed"}
    assert any(entry["kind"] == "run_error" for entry in transcript)


def test_an_unknown_provider_is_rejected_rather_than_defaulted():
    """A typo must not quietly bill a different vendor."""
    with pytest.raises(ValueError):
        service.build_model_client("clyde")
