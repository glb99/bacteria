"""Invariant tests for the Gemini client — the second implementation of the protocol.

Two things are under test. First, parity: a second provider must classify
failures the same way the first does, or callers end up branching on which
provider they got. Second, translation: the runtime speaks Anthropic's block
shapes, so this client has to convert them faithfully in both directions, and
that conversion is where a drop-in provider actually costs something.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bacteria.model.errors import AssetError, ContractError, CredentialsError, ServingError
from bacteria.model.gemini_client import GeminiClient
from bacteria.model.protocol import SendsMessages
from bacteria.runtime.runtime import Runtime
from bacteria.session.store import SessionStore
from google.genai import errors as genai_errors


def make_client(**overrides) -> GeminiClient:
    client = GeminiClient(api_key="test-key", max_retries=2, backoff_seconds=0, **overrides)
    client._client = MagicMock()
    # The client calls the SDK's async surface (`.aio`), so that is what the
    # tests must drive. Mocking `.models` instead would leave the real `.aio`
    # in place and attempt a network call.
    client._client.aio.models.generate_content = AsyncMock()
    return client


def fake_response(
    text="hello", function_calls=None, finish_reason="STOP", model_version="gemini-3.5-flash"
):
    """Build a stand-in Gemini response.

    Entries in ``function_calls`` may carry an optional ``"signature"`` key,
    simulating the ``thought_signature`` the real API attaches to a function
    call part.

    ``model_version`` is what the real response reports and what a run records.
    It is optional on the response type; pass ``None`` for the case where the
    provider does not say.
    """
    parts = [
        SimpleNamespace(
            function_call=SimpleNamespace(id=c.get("id"), name=c["name"], args=c["input"]),
            thought_signature=c.get("signature"),
        )
        for c in (function_calls or [])
    ]
    candidate = SimpleNamespace(finish_reason=finish_reason, content=SimpleNamespace(parts=parts))
    return SimpleNamespace(text=text, candidates=[candidate], model_version=model_version)


def make_api_error(cls, code, message="boom"):
    return cls(code=code, response_json={"error": {"message": message}})


async def test_serving_failure_is_retried_with_identical_request_then_succeeds():
    client = make_client()
    client._client.aio.models.generate_content.side_effect = [
        make_api_error(genai_errors.ServerError, 500),
        fake_response(text="ok"),
    ]

    result = await client.send(messages=[{"role": "user", "content": "hi"}])

    assert result.text == "ok"
    assert client._client.aio.models.generate_content.call_count == 2
    first_call, second_call = client._client.aio.models.generate_content.call_args_list
    assert first_call == second_call  # identical request both times


async def test_serving_failure_exhausts_retries_and_raises():
    client = make_client()
    client._client.aio.models.generate_content.side_effect = make_api_error(
        genai_errors.ServerError, 500
    )

    with pytest.raises(ServingError):
        await client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.aio.models.generate_content.call_count == 1 + client.max_retries


async def test_rate_limit_is_a_retryable_serving_error_despite_being_a_client_error():
    """429 must retry, even though the SDK files it under ClientError.

    The SDK splits by HTTP range, which does not line up with retryability.
    Classified by range alone, a rate limit would fail on the first attempt.
    """
    client = make_client()
    client._client.aio.models.generate_content.side_effect = [
        make_api_error(genai_errors.ClientError, 429),
        fake_response(text="ok"),
    ]

    result = await client.send(messages=[{"role": "user", "content": "hi"}])

    assert result.text == "ok"
    assert client._client.aio.models.generate_content.call_count == 2


async def test_credentials_failure_is_not_retried():
    client = make_client()
    client._client.aio.models.generate_content.side_effect = make_api_error(
        genai_errors.ClientError, 401, message="invalid api key"
    )

    with pytest.raises(CredentialsError):
        await client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.aio.models.generate_content.call_count == 1


async def test_asset_failure_is_not_retried():
    client = make_client()
    client._client.aio.models.generate_content.side_effect = make_api_error(
        genai_errors.ClientError, 400, message="maximum context length exceeded"
    )

    with pytest.raises(AssetError):
        await client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.aio.models.generate_content.call_count == 1


async def test_contract_failure_is_not_retried():
    client = make_client()
    client._client.aio.models.generate_content.side_effect = make_api_error(
        genai_errors.ClientError, 400, message="unknown field 'foo'"
    )

    with pytest.raises(ContractError):
        await client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.aio.models.generate_content.call_count == 1


async def test_tool_calls_are_surfaced_as_proposals_with_synthetic_ids():
    client = make_client()
    client._client.aio.models.generate_content.return_value = fake_response(
        text=None,
        function_calls=[{"name": "get_time", "input": {}}],
        finish_reason="STOP",
    )

    result = await client.send(messages=[{"role": "user", "content": "what time is it?"}])

    assert result.tool_calls == [{"id": "call_0", "name": "get_time", "input": {}}]
    # Reported, not run. The synthetic id exists because Gemini does not always
    # issue one, and the internal format needs it to correlate the result.


async def test_the_serving_model_is_reported_and_is_none_when_unstated():
    """What answered, or an honest null — never the name we asked for.

    ADR 0019 puts `model` on the response precisely so a run records an
    observation rather than an intention, so substituting the configured name
    when the provider stays quiet would defeat the field. `model_version` is
    optional on the response type, making the quiet case real rather than
    hypothetical.

    Written because the first implementation did substitute it, reaching for
    `self.model` inside a `@staticmethod` — a `NameError` on any response
    without a version, invisible to every test here because the fake always
    supplied one.
    """
    client = make_client()

    client._client.aio.models.generate_content.return_value = fake_response(
        model_version="gemini-3.5-flash-002"
    )
    named = await client.send(messages=[{"role": "user", "content": "hi"}])
    assert named.model == "gemini-3.5-flash-002"

    client._client.aio.models.generate_content.return_value = fake_response(model_version=None)
    unstated = await client.send(messages=[{"role": "user", "content": "hi"}])
    assert unstated.model is None


async def test_text_messages_translate_user_and_assistant_roles():
    client = make_client()
    client._client.aio.models.generate_content.return_value = fake_response(text="ok")

    await client.send(
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
    )

    contents = client._client.aio.models.generate_content.call_args.kwargs["contents"]
    assert [c.role for c in contents] == ["user", "model"]
    assert contents[0].parts[0].text == "hi"
    assert contents[1].parts[0].text == "hello"


async def test_tool_use_and_tool_result_blocks_translate_to_function_call_and_response():
    """Tool blocks translate in both directions, including the role remapping.

    This is the real test of the seam. Plain text would pass with almost any
    implementation; tool exchanges are where the two formats genuinely differ —
    Anthropic marks a tool result as a ``user`` message, Gemini needs a ``tool``
    role, and the function name has to be recovered from the earlier call
    because the result block carries only an id.
    """
    client = make_client()
    client._client.aio.models.generate_content.return_value = fake_response(text="done")

    messages = [
        {"role": "user", "content": "what time is it?"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "call_0", "name": "get_time", "input": {}}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call_0", "content": "10:00"}],
        },
    ]

    await client.send(messages=messages)

    contents = client._client.aio.models.generate_content.call_args.kwargs["contents"]
    assert contents[1].role == "model"
    assert contents[1].parts[0].function_call.name == "get_time"
    assert contents[2].role == "tool"
    assert contents[2].parts[0].function_response.name == "get_time"
    assert contents[2].parts[0].function_response.response == {"result": "10:00"}


async def test_thought_signature_is_captured_and_echoed_back_on_the_next_turn():
    """Opaque provider state survives a round trip through the runtime.

    Found against the real API, not in mocks — every mocked test passed while
    live tool calls failed with ``Function call is missing a
    thought_signature``. Gemini attaches that token to a function call part and
    requires it echoed back verbatim on the next turn. Two ways to lose it, and
    this covers both: reading ``response.function_calls`` (the convenience
    property, which drops it) on the way out, and failing to re-attach it on
    the way back in.

    Regression value is high and cheap: the failure is invisible to every
    single-turn test and fatal to every multi-turn one.
    """
    client = make_client()
    client._client.aio.models.generate_content.return_value = fake_response(
        text=None,
        function_calls=[
            {"id": "call_0", "name": "get_time", "input": {}, "signature": b"opaque-sig"}
        ],
    )

    result = await client.send(messages=[{"role": "user", "content": "what time is it?"}])
    assert result.tool_calls == [
        {
            "id": "call_0",
            "name": "get_time",
            "input": {},
            "provider_data": {"thought_signature": b"opaque-sig"},
        }
    ]

    # Simulate Runtime re-sending that same tool_use block on the follow-up call
    follow_up = {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "call_0",
                "name": "get_time",
                "input": {},
                "provider_data": {"thought_signature": b"opaque-sig"},
            }
        ],
    }
    client._client.aio.models.generate_content.return_value = fake_response(text="done")
    await client.send(messages=[follow_up])

    contents = client._client.aio.models.generate_content.call_args.kwargs["contents"]
    assert contents[0].parts[0].thought_signature == b"opaque-sig"


async def test_missing_credentials_at_construction_is_classified_not_raw(monkeypatch):
    """A missing key fails at construction here, not on the first call.

    This SDK validates eagerly and raises a bare ValueError, so the failure
    never reaches send()'s handler. Left unclassified it would escape the error
    taxonomy entirely — the same gap the Anthropic client has at a different
    point in its lifecycle.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(CredentialsError):
        GeminiClient(api_key=None)


async def test_gemini_client_satisfies_the_sends_messages_protocol():
    """The runtime accepts this client with no changes of its own.

    The weakest test in this file and worth keeping anyway: ``isinstance``
    against a runtime-checkable protocol confirms only that the method exists,
    not that it behaves. The tests above are what establish the behavior.
    """
    client = GeminiClient(api_key="test-key")
    assert isinstance(client, SendsMessages)

    store = SessionStore()
    runtime = Runtime(model_client=client, session_store=store)
    assert runtime is not None
