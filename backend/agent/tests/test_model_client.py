"""Invariant tests for the Anthropic client: what is retried, and what is not.

Retry classification is the load-bearing behavior here. Getting it wrong is
expensive in both directions: retrying a non-transient failure burns quota to
fail identically, and not retrying a transient one turns a blip into an outage.
Each test therefore asserts the call *count* as well as the exception type.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import anthropic
import pytest

from bacteria.agent.model.client import ModelClient
from bacteria.agent.model.errors import AssetError, ContractError, CredentialsError, ServingError


def make_client(**overrides) -> ModelClient:
    client = ModelClient(api_key="test-key", max_retries=2, backoff_seconds=0, **overrides)
    client._client = MagicMock()
    # `create` specifically must be an AsyncMock: the client awaits it, and a
    # plain MagicMock returns something un-awaitable that fails as a
    # ContractError rather than as the case under test.
    client._client.messages.create = AsyncMock()
    return client


def fake_response(text="hello", tool_calls=None, stop_reason="end_turn", model="claude-sonnet-4-5"):
    content = [SimpleNamespace(type="text", text=text)] if text is not None else []
    for tc in tool_calls or []:
        content.append(
            SimpleNamespace(type="tool_use", id=tc["id"], name=tc["name"], input=tc["input"])
        )
    # `model` is on the real Message and is what a run records, so the fake
    # carries it too — a fake missing a field the code reads tests a shape the
    # provider does not return.
    return SimpleNamespace(content=content, stop_reason=stop_reason, model=model)


def make_api_error(exc_cls, message="boom"):
    request = MagicMock()
    if exc_cls is anthropic.RateLimitError or exc_cls is anthropic.BadRequestError:
        response = MagicMock()
        response.status_code = 429 if exc_cls is anthropic.RateLimitError else 400
        return exc_cls(message, response=response, body=None)
    if exc_cls is anthropic.APITimeoutError:
        return exc_cls(request)
    if exc_cls is anthropic.APIConnectionError:
        return exc_cls(message=message, request=request)
    if exc_cls is anthropic.InternalServerError:
        response = MagicMock()
        response.status_code = 500
        return exc_cls(message, response=response, body=None)
    if exc_cls is anthropic.AuthenticationError:
        response = MagicMock()
        response.status_code = 401
        return exc_cls(message, response=response, body=None)
    raise AssertionError(f"unhandled exc_cls {exc_cls}")


async def test_serving_failure_is_retried_with_identical_request_then_succeeds():
    """A retry re-sends the identical request and does nothing else.

    That identity is what makes retrying safe: there is no side effect in this
    module for a second attempt to duplicate.
    """
    client = make_client()
    client._client.messages.create.side_effect = [
        make_api_error(anthropic.RateLimitError),
        fake_response(text="ok"),
    ]

    result = await client.send(messages=[{"role": "user", "content": "hi"}])

    assert result.text == "ok"
    assert client._client.messages.create.call_count == 2
    first_call, second_call = client._client.messages.create.call_args_list
    assert first_call == second_call  # identical request both times


async def test_serving_failure_exhausts_retries_and_raises():
    client = make_client()
    client._client.messages.create.side_effect = anthropic.APITimeoutError(MagicMock())

    with pytest.raises(ServingError):
        await client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.messages.create.call_count == 1 + client.max_retries


async def test_asset_failure_is_not_retried():
    client = make_client()
    client._client.messages.create.side_effect = make_api_error(
        anthropic.BadRequestError, message="maximum context length exceeded"
    )

    with pytest.raises(AssetError):
        await client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.messages.create.call_count == 1


async def test_contract_failure_is_not_retried():
    client = make_client()
    client._client.messages.create.side_effect = make_api_error(
        anthropic.BadRequestError, message="unknown field 'foo'"
    )

    with pytest.raises(ContractError):
        await client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.messages.create.call_count == 1


async def test_missing_credentials_is_not_retried():
    """A missing key surfaces as a bare TypeError, before any network call.

    It belongs to no SDK exception hierarchy, so a client that only classifies
    the SDK's own errors lets it escape untyped. Sweeping it into ContractError
    would hide the one failure an operator can actually fix.
    """
    client = make_client()
    client._client.messages.create.side_effect = TypeError(
        "Could not resolve authentication method. Expected one of api_key, "
        "auth_token, or credentials to be set."
    )

    with pytest.raises(CredentialsError):
        await client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.messages.create.call_count == 1


async def test_rejected_credentials_is_not_retried():
    """A rejected key (401) classifies the same as a missing one.

    Different origin — this request reached the server — but the same thing is
    wrong and the same person has to fix it.
    """
    client = make_client()
    client._client.messages.create.side_effect = make_api_error(
        anthropic.AuthenticationError, message="invalid x-api-key"
    )

    with pytest.raises(CredentialsError):
        await client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.messages.create.call_count == 1


async def test_tool_calls_are_surfaced_as_proposals_not_executed():
    """The client reports a requested tool call and never acts on it.

    Uses a deliberately alarming tool name: if the model layer ever gained the
    ability to execute what it reports, this is what that would look like.
    """
    client = make_client()
    client._client.messages.create.return_value = fake_response(
        text=None,
        tool_calls=[{"id": "t1", "name": "delete_file", "input": {"path": "/etc/passwd"}}],
        stop_reason="tool_use",
    )

    result = await client.send(messages=[{"role": "user", "content": "hi"}])

    assert result.tool_calls == [
        {"id": "t1", "name": "delete_file", "input": {"path": "/etc/passwd"}}
    ]
    # No filesystem module is imported or touched anywhere in this module —
    # structurally, the client has no way to execute what it reports.
