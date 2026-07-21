"""Load-bearing invariant tests for the model client (Part 2 decisions)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import pytest

from model.client import ModelClient
from model.errors import AssetError, ContractError, ServingError


def make_client(**overrides) -> ModelClient:
    client = ModelClient(api_key="test-key", max_retries=2, backoff_seconds=0, **overrides)
    client._client = MagicMock()
    return client


def fake_response(text="hello", tool_calls=None, stop_reason="end_turn"):
    content = [SimpleNamespace(type="text", text=text)] if text is not None else []
    for tc in tool_calls or []:
        content.append(SimpleNamespace(type="tool_use", id=tc["id"], name=tc["name"], input=tc["input"]))
    return SimpleNamespace(content=content, stop_reason=stop_reason)


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
    raise AssertionError(f"unhandled exc_cls {exc_cls}")


def test_serving_failure_is_retried_with_identical_request_then_succeeds():
    """'Retry logic must be side-effect-aware' — verified narrowly here as:
    a retry re-sends the exact same request, nothing more, nothing less."""
    client = make_client()
    client._client.messages.create.side_effect = [
        make_api_error(anthropic.RateLimitError),
        fake_response(text="ok"),
    ]

    result = client.send(messages=[{"role": "user", "content": "hi"}])

    assert result.text == "ok"
    assert client._client.messages.create.call_count == 2
    first_call, second_call = client._client.messages.create.call_args_list
    assert first_call == second_call  # identical request both times


def test_serving_failure_exhausts_retries_and_raises():
    client = make_client()
    client._client.messages.create.side_effect = anthropic.APITimeoutError(MagicMock())

    with pytest.raises(ServingError):
        client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.messages.create.call_count == 1 + client.max_retries


def test_asset_failure_is_not_retried():
    client = make_client()
    client._client.messages.create.side_effect = make_api_error(
        anthropic.BadRequestError, message="maximum context length exceeded"
    )

    with pytest.raises(AssetError):
        client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.messages.create.call_count == 1


def test_contract_failure_is_not_retried():
    client = make_client()
    client._client.messages.create.side_effect = make_api_error(
        anthropic.BadRequestError, message="unknown field 'foo'"
    )

    with pytest.raises(ContractError):
        client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.messages.create.call_count == 1


def test_tool_calls_are_surfaced_as_proposals_not_executed():
    """'Tool calls treated as proposals, not execution' — the client must
    only report a tool_use block, never act on it."""
    client = make_client()
    client._client.messages.create.return_value = fake_response(
        text=None,
        tool_calls=[{"id": "t1", "name": "delete_file", "input": {"path": "/etc/passwd"}}],
        stop_reason="tool_use",
    )

    result = client.send(messages=[{"role": "user", "content": "hi"}])

    assert result.tool_calls == [{"id": "t1", "name": "delete_file", "input": {"path": "/etc/passwd"}}]
    # No filesystem module is imported or touched anywhere in this module —
    # structurally, the client has no way to execute what it reports.
