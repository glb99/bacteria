"""Authorization over HTTP: whose sessions a caller can reach.

These are the tests that would have caught the hole this feature closed — before
it, any caller could name any `user_id` and read any session id they could
guess. Each asserts a refusal, because a passing "allowed" test says nothing
about whether anything is denied.
"""

import pytest
from bacteria.model.protocol import ModelResponse
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from fastpaip.auth.service import issue_key, revoke_key
from fastpaip.auth import keys
from fastpaip.chat import service
from fastpaip.core.db import session_scope
from fastpaip.views import create_app, lifespan_running


class FakeModelClient:
    async def send(self, messages, **kwargs) -> ModelResponse:
        return ModelResponse(text="ok", tool_calls=[], stop_reason="end_turn", raw=None)


@pytest.fixture(name="engine")
def _engine():
    return create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture(name="client")
def _client(engine, monkeypatch):
    async def _create_tables():
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    async def _test_session():
        async with AsyncSession(engine) as session:
            yield session

    monkeypatch.setitem(service.PROVIDERS, "fake", FakeModelClient)
    monkeypatch.setenv("FASTPAIP_MODEL_PROVIDER", "fake")

    app = create_app(lifespan=lifespan_running(_create_tables))
    app.dependency_overrides[session_scope] = _test_session
    with TestClient(app) as client:
        yield client


@pytest.fixture(name="issue")
def _issue(engine):
    async def _make(principal_id: str) -> str:
        async with AsyncSession(engine) as session:
            return await issue_key(session, principal_id=principal_id, label=principal_id)

    return _make


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_an_unauthenticated_request_is_refused(client):
    """No credential means no access, on every route.

    Checked across all of them rather than one, because the failure mode is a
    route added later without the dependency — and nothing else would notice.
    """
    assert client.post("/chat/sessions").status_code == 401
    assert client.get("/chat/sessions/anything/transcript").status_code == 401
    assert client.post("/chat/sessions/anything/turns", json={"text": "hi"}).status_code == 401
    assert client.post(
        "/ingestion/batches", json={"source": "s", "records": [{"external_id": "1", "name": "n"}]}
    ).status_code == 401


async def test_an_unknown_key_is_refused(client):
    fabricated = keys.generate().token

    assert client.post("/chat/sessions", headers=auth(fabricated)).status_code == 401


async def test_a_wrong_secret_for_a_real_key_id_is_refused(client, issue):
    """Knowing a key id must be worth nothing on its own.

    The id is stored in the clear and appears in logs, so it should be assumed
    known. Only the secret is a secret.
    """
    token = await issue("acme")
    key_id, _secret = keys.split(token)
    forged = f"fp_{key_id}_{keys.generate().token.split('_')[2]}"

    assert client.post("/chat/sessions", headers=auth(forged)).status_code == 401


async def test_a_revoked_key_stops_working(client, issue, engine):
    token = await issue("acme")
    assert client.post("/chat/sessions", headers=auth(token)).status_code == 201

    key_id, _secret = keys.split(token)
    async with AsyncSession(engine) as session:
        await revoke_key(session, key_id=key_id)

    assert client.post("/chat/sessions", headers=auth(token)).status_code == 401


async def test_a_session_is_owned_by_the_authenticated_caller_not_a_claimed_id(client, issue):
    """The owner comes from the credential, and the client cannot name it.

    The route previously took `user_id` in the body, which meant anyone could
    create a session as anyone else and then read it legitimately.
    """
    token = await issue("acme")

    body = client.post(
        "/chat/sessions", headers=auth(token), json={"user_id": "someone-else"}
    ).json()

    assert body["user_id"] == "acme"


async def test_one_principal_cannot_read_anothers_transcript(client, issue):
    """The hole this feature exists to close.

    404 rather than 403 on purpose: a 403 confirms the session exists, which
    turns a session id into an oracle for enumeration.
    """
    owner, intruder = await issue("acme"), await issue("rival")
    session_id = client.post("/chat/sessions", headers=auth(owner)).json()["session_id"]
    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(owner), json={"text": "secret"})

    response = client.get(f"/chat/sessions/{session_id}/transcript", headers=auth(intruder))

    assert response.status_code == 404
    assert "secret" not in response.text


async def test_one_principal_cannot_take_a_turn_in_anothers_session(client, issue):
    """Refused before the model is called, not after.

    A turn costs money and writes to the transcript. Checking ownership
    afterwards would let an intruder do both and merely not see the reply.
    """
    owner, intruder = await issue("acme"), await issue("rival")
    session_id = client.post("/chat/sessions", headers=auth(owner)).json()["session_id"]

    response = client.post(
        f"/chat/sessions/{session_id}/turns", headers=auth(intruder), json={"text": "inject"}
    )
    assert response.status_code == 404

    transcript = client.get(
        f"/chat/sessions/{session_id}/transcript", headers=auth(owner)
    ).json()
    assert transcript == []


async def test_a_missing_session_and_a_forbidden_one_are_indistinguishable(client, issue):
    """Both 404, so an id cannot be probed for existence."""
    owner, intruder = await issue("acme"), await issue("rival")
    real = client.post("/chat/sessions", headers=auth(owner)).json()["session_id"]

    forbidden = client.get(f"/chat/sessions/{real}/transcript", headers=auth(intruder))
    absent = client.get("/chat/sessions/no-such-session/transcript", headers=auth(intruder))

    assert forbidden.status_code == absent.status_code == 404
    assert forbidden.json() == absent.json()


async def test_the_owner_still_has_access(client, issue):
    """The refusals above must not have been achieved by refusing everyone."""
    token = await issue("acme")
    session_id = client.post("/chat/sessions", headers=auth(token)).json()["session_id"]

    client.post(f"/chat/sessions/{session_id}/turns", headers=auth(token), json={"text": "hi"})
    transcript = client.get(f"/chat/sessions/{session_id}/transcript", headers=auth(token)).json()

    assert [entry["payload"]["text"] for entry in transcript if "text" in entry["payload"]] == [
        "hi",
        "ok",
    ]
