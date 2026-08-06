"""Load-bearing invariant tests for GeminiClient — the second SendsMessages
implementation, proving the Protocol seam from Part 2 actually holds."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.genai import errors as genai_errors

from bacteria.model.errors import AssetError, ContractError, CredentialsError, ServingError
from bacteria.model.gemini_client import GeminiClient
from bacteria.runtime.runtime import Runtime, SendsMessages
from bacteria.session.store import SessionStore


def make_client(**overrides) -> GeminiClient:
    client = GeminiClient(api_key="test-key", max_retries=2, backoff_seconds=0, **overrides)
    client._client = MagicMock()
    return client


def fake_response(text="hello", function_calls=None, finish_reason="STOP"):
    """function_calls entries may include an optional "signature" key to
    simulate a thinking model's thought_signature on that part."""
    parts = [
        SimpleNamespace(
            function_call=SimpleNamespace(id=c.get("id"), name=c["name"], args=c["input"]),
            thought_signature=c.get("signature"),
        )
        for c in (function_calls or [])
    ]
    candidate = SimpleNamespace(finish_reason=finish_reason, content=SimpleNamespace(parts=parts))
    return SimpleNamespace(text=text, candidates=[candidate])


def make_api_error(cls, code, message="boom"):
    return cls(code=code, response_json={"error": {"message": message}})


def test_serving_failure_is_retried_with_identical_request_then_succeeds():
    client = make_client()
    client._client.models.generate_content.side_effect = [
        make_api_error(genai_errors.ServerError, 500),
        fake_response(text="ok"),
    ]

    result = client.send(messages=[{"role": "user", "content": "hi"}])

    assert result.text == "ok"
    assert client._client.models.generate_content.call_count == 2
    first_call, second_call = client._client.models.generate_content.call_args_list
    assert first_call == second_call  # identical request both times


def test_serving_failure_exhausts_retries_and_raises():
    client = make_client()
    client._client.models.generate_content.side_effect = make_api_error(
        genai_errors.ServerError, 500
    )

    with pytest.raises(ServingError):
        client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.models.generate_content.call_count == 1 + client.max_retries


def test_rate_limit_is_a_retryable_serving_error_despite_being_a_client_error():
    """429 is technically a ClientError (400-499) in the SDK's own hierarchy —
    must still be classified as ServingError, or a rate limit would never retry."""
    client = make_client()
    client._client.models.generate_content.side_effect = [
        make_api_error(genai_errors.ClientError, 429),
        fake_response(text="ok"),
    ]

    result = client.send(messages=[{"role": "user", "content": "hi"}])

    assert result.text == "ok"
    assert client._client.models.generate_content.call_count == 2


def test_credentials_failure_is_not_retried():
    client = make_client()
    client._client.models.generate_content.side_effect = make_api_error(
        genai_errors.ClientError, 401, message="invalid api key"
    )

    with pytest.raises(CredentialsError):
        client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.models.generate_content.call_count == 1


def test_asset_failure_is_not_retried():
    client = make_client()
    client._client.models.generate_content.side_effect = make_api_error(
        genai_errors.ClientError, 400, message="maximum context length exceeded"
    )

    with pytest.raises(AssetError):
        client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.models.generate_content.call_count == 1


def test_contract_failure_is_not_retried():
    client = make_client()
    client._client.models.generate_content.side_effect = make_api_error(
        genai_errors.ClientError, 400, message="unknown field 'foo'"
    )

    with pytest.raises(ContractError):
        client.send(messages=[{"role": "user", "content": "hi"}])

    assert client._client.models.generate_content.call_count == 1


def test_tool_calls_are_surfaced_as_proposals_with_synthetic_ids():
    client = make_client()
    client._client.models.generate_content.return_value = fake_response(
        text=None,
        function_calls=[{"name": "get_time", "input": {}}],
        finish_reason="STOP",
    )

    result = client.send(messages=[{"role": "user", "content": "what time is it?"}])

    assert result.tool_calls == [{"id": "call_0", "name": "get_time", "input": {}}]
    # No handler is ever invoked here — the client only reports the proposal,
    # same invariant as ModelClient (Part 6): the model layer never executes.


def test_text_messages_translate_user_and_assistant_roles():
    client = make_client()
    client._client.models.generate_content.return_value = fake_response(text="ok")

    client.send(
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
    )

    contents = client._client.models.generate_content.call_args.kwargs["contents"]
    assert [c.role for c in contents] == ["user", "model"]
    assert contents[0].parts[0].text == "hi"
    assert contents[1].parts[0].text == "hello"


def test_tool_use_and_tool_result_blocks_translate_to_function_call_and_response():
    """Runtime (Part 6/7) constructs tool_use/tool_result blocks in Anthropic's
    wire shape; a real drop-in provider has to translate those, not just
    plain text — this is the actual test of the SendsMessages seam."""
    client = make_client()
    client._client.models.generate_content.return_value = fake_response(text="done")

    messages = [
        {"role": "user", "content": "what time is it?"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "call_0", "name": "get_time", "input": {}}],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_0", "content": "10:00"}
            ],
        },
    ]

    client.send(messages=messages)

    contents = client._client.models.generate_content.call_args.kwargs["contents"]
    assert contents[1].role == "model"
    assert contents[1].parts[0].function_call.name == "get_time"
    assert contents[2].role == "tool"
    assert contents[2].parts[0].function_response.name == "get_time"
    assert contents[2].parts[0].function_response.response == {"result": "10:00"}


def test_thought_signature_is_captured_and_echoed_back_on_the_next_turn():
    """Found against the real API, not in mocks: thinking models attach a
    thought_signature to function_call parts that must be echoed back
    verbatim on the follow-up turn, or Gemini rejects the request outright
    ('Function call is missing a thought_signature'). response.function_calls
    (the convenience property) drops it — _to_model_response must read the
    real parts instead, and _to_content must re-attach it when the block
    round-trips back through Runtime's follow-up message."""
    client = make_client()
    client._client.models.generate_content.return_value = fake_response(
        text=None,
        function_calls=[{"id": "call_0", "name": "get_time", "input": {}, "signature": b"opaque-sig"}],
    )

    result = client.send(messages=[{"role": "user", "content": "what time is it?"}])
    assert result.tool_calls == [
        {"id": "call_0", "name": "get_time", "input": {}, "provider_data": {"thought_signature": b"opaque-sig"}}
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
    client._client.models.generate_content.return_value = fake_response(text="done")
    client.send(messages=[follow_up])

    contents = client._client.models.generate_content.call_args.kwargs["contents"]
    assert contents[0].parts[0].thought_signature == b"opaque-sig"


def test_missing_credentials_at_construction_is_classified_not_raw(monkeypatch):
    """genai.Client() fails eagerly at construction (unlike Anthropic's lazy
    failure on first send()) with a bare ValueError — must still surface as
    CredentialsError, not leak the SDK's raw exception type."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(CredentialsError):
        GeminiClient(api_key=None)


def test_gemini_client_satisfies_the_sends_messages_protocol():
    """The whole point of building a second client: Runtime must accept it
    with zero changes, via the structural SendsMessages Protocol."""
    client = GeminiClient(api_key="test-key")
    assert isinstance(client, SendsMessages)

    store = SessionStore()
    runtime = Runtime(model_client=client, session_store=store)
    assert runtime is not None
