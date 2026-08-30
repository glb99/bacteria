"""Browser sessions: what a cookie may prove, and for how long.

The two paths `test_personal_access.py` exempts from its route enumeration are
asserted here instead, which is the deal that exemption makes. Everything else
leans toward asserting refusals, for the reason `test_auth.py` gives: a wrong
answer means an unauthorized caller treated as an authorized one.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.auth import keys
from bacteria.app.auth.dependencies import COOKIE_NAME
from bacteria.app.auth.models import BrowserSession
from bacteria.app.auth.service import issue_key, revoke_key
from bacteria.app.core.db import session_scope
from bacteria.app.views import create_app


@pytest.fixture(name="client")
def _client(engine, backend_options):
    async def _test_session():
        async with AsyncSession(engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[session_scope] = _test_session
    # `https`, and not as decoration. The cookie is set `Secure`, and httpx
    # honours that -- over the default `http://testserver` it stores the cookie
    # and never sends it, so every assertion here passes for the wrong reason:
    # the 401s are "no credential presented" rather than "credential refused".
    # Three tests were green that way before this line existed.
    with TestClient(app, base_url="https://testserver", backend_options=backend_options) as client:
        yield client


def authenticated(client: TestClient) -> bool:
    """Whether the client's current credentials reach a route.

    `POST /chat/sessions` rather than a transcript read, because it takes no
    path parameter: a transcript request for a session id that does not exist
    answers 404 *after* authenticating, so it cannot tell "refused" from
    "authenticated and absent". That mistake is why this helper exists.
    """
    return client.post("/chat/sessions").status_code == 201


@pytest.fixture(name="key")
async def _key(engine):
    async with AsyncSession(engine) as session:
        return await issue_key(session, principal_id="acme", label="console")


def open_session(client: TestClient, key: str):
    return client.post("/auth/session", json={"key": key})


async def test_a_key_buys_a_cookie_that_authenticates(client, key):
    """The whole point: after the exchange, no request carries the key again.

    If the cookie did not authenticate, a console would have to keep the key to
    make any request at all — which is the thing `frontend/README.md` called a
    real gap, arrived at by a longer route.
    """
    opened = open_session(client, key)

    assert opened.status_code == 200
    assert opened.json()["principal_id"] == "acme"
    assert COOKIE_NAME in client.cookies

    # No Authorization header anywhere in this call.
    assert authenticated(client)


async def test_the_token_is_never_in_the_response_body(client, key):
    """A token `fetch` can read is a token an injected script can read.

    HttpOnly is the entire mechanism here, and returning the same value in JSON
    would hand it to the page anyway — a mistake that leaves every other part of
    this working perfectly.
    """
    body = open_session(client, key).text

    cookie = client.cookies[COOKIE_NAME]
    assert cookie.startswith(f"{keys.SESSION_PREFIX}_")
    assert cookie not in body


async def test_the_cookie_is_httponly_secure_and_strict(client, key):
    """Any one of the three missing turns the exchange into theatre.

    Without HttpOnly a script reads it; without Secure a plain-HTTP hop leaks
    it; without SameSite=Strict another origin can spend it, and there is no
    CSRF token standing behind that decision.
    """
    header = open_session(client, key).headers["set-cookie"].lower()

    assert "httponly" in header
    assert "secure" in header
    assert "samesite=strict" in header


async def test_a_bad_key_is_refused_and_leaves_no_cookie(client):
    """A 401 that still opened a session would be the worst of both.

    This route is unauthenticated and takes the key in a body, so it is the most
    attractive place on the service to test guesses against. It must answer
    exactly like every other failure.
    """
    refused = open_session(client, "fp_deadbeefdeadbeef_notarealsecret")

    assert refused.status_code == 401
    assert COOKIE_NAME not in client.cookies


async def test_a_revoked_key_cannot_open_a_session(client, key, engine):
    """Revocation has to reach the exchange, not only the routes.

    The reason this is a separate test from the one above: a second
    verification that forgot `is_active` would pass every "bad key" case and
    still hand a live cookie to a credential the operator had already killed.
    """
    key_id, _secret = keys.split(key)
    async with AsyncSession(engine) as session:
        await revoke_key(session, key_id=key_id)

    assert open_session(client, key).status_code == 401


async def test_an_expired_session_stops_working(client, key, engine):
    """Expiry is the reason this table exists rather than columns on api_key.

    Checked by ageing the row rather than by waiting twelve hours. If
    `is_active` consulted only `revoked_at`, every session would be immortal and
    nothing else in this file would notice.
    """
    open_session(client, key)
    session_id, _secret = keys.split(client.cookies[COOKIE_NAME], keys.SESSION_PREFIX)

    async with AsyncSession(engine) as session:
        row = await session.get(BrowserSession, session_id)
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.add(row)
        await session.commit()

    assert not authenticated(client)


async def test_logging_out_makes_the_cookie_stop_working(client, key):
    """Log out has to end the session server-side, not just clear the cookie.

    Clearing only the browser's copy leaves a live credential in whatever
    already captured it, which is exactly the case someone logs out for.
    """
    open_session(client, key)
    token = client.cookies[COOKIE_NAME]

    assert client.delete("/auth/session").status_code == 204

    client.cookies.set(COOKIE_NAME, token)
    assert not authenticated(client)


async def test_logging_out_needs_the_secret_not_just_the_id(client, key):
    """Otherwise logout is an unauthenticated write against any id you can name.

    Session ids are not secret — this service prints them in its own failure
    logs — so revoking on the id alone would let anyone who read a log end
    somebody's session.
    """
    open_session(client, key)
    real = client.cookies[COOKIE_NAME]
    session_id, _secret = keys.split(real, keys.SESSION_PREFIX)

    client.cookies.set(COOKIE_NAME, f"{keys.SESSION_PREFIX}_{session_id}_wrongsecret")
    assert client.delete("/auth/session").status_code == 204

    client.cookies.set(COOKIE_NAME, real)
    assert authenticated(client)


async def test_logging_out_without_a_session_is_still_204(client):
    """Answering differently would turn logout into a test for a live id."""
    assert client.delete("/auth/session").status_code == 204


async def test_a_session_token_is_not_a_bearer_key(client, key):
    """The prefixes are what keep the two credentials apart.

    A session is deliberately weaker than a key — it expires, and it is held
    somewhere less safe. Letting one be presented where the other belongs erases
    the distinction the whole design rests on.
    """
    open_session(client, key)
    token = client.cookies[COOKIE_NAME]
    client.cookies.clear()

    refused = client.post("/chat/sessions", headers={"Authorization": f"Bearer {token}"})
    assert refused.status_code == 401


async def test_an_api_key_is_not_a_session_cookie(client, key):
    """The other direction, which matters more.

    A key in a cookie is a key a script can be tricked into sending from
    anywhere, and it never expires. If this were accepted, pasting a key into
    the wrong box would silently create the exact credential-in-the-browser
    situation the session exists to avoid.
    """
    client.cookies.set(COOKIE_NAME, key)

    assert not authenticated(client)


async def test_a_bearer_key_still_wins_over_a_cookie(client, key, engine):
    """Sessions must not change what a key-carrying request does.

    Every existing client sends a bearer header, and a console tab open beside a
    terminal is an ordinary thing. If the cookie were consulted first, one dead
    cookie would start failing requests that carry a perfectly good key.
    """
    other = None
    async with AsyncSession(engine) as session:
        other = await issue_key(session, principal_id="rival", label="cli")

    open_session(client, key)
    client.cookies.set(COOKIE_NAME, "bs_deadbeefdeadbeef_garbage")

    response = client.post("/chat/sessions", headers={"Authorization": f"Bearer {other}"})
    assert response.status_code == 201
