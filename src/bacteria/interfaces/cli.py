"""Minimal CLI entry point — Layer 1 (Interfaces and channels).

Not tied to any article Part: Part 1's systems map names this layer, but
the series never gives it a dedicated deep-dive the way it does layers 2-9
(Parts 2-8 map onto those one-to-one). This is a deliberately minimal real
entry point, built to close two previously-flagged gaps: no real (non-mocked)
call to ModelClient existed anywhere in the codebase, and no code outside
tests drove Runtime end-to-end. It constructs the real ModelClient,
SessionStore, and Runtime and hands work — a line of user input — to
Runtime.run_turn(), which is this layer's whole job per Part 1: receive
work from outside, then hand it to the control plane/runtime.

Also owns building the tool registry — nothing else in this project has a
notion of "what capabilities does this deployment have" yet, so that
construction lives here alongside the other real objects (same reasoning
as ModelClient/SessionStore). `add_note` (bacteria.tools.notes) is the
first real tool registered anywhere in this project, deliberately small
but with an actual side effect, gated by the real approval boundary
(cli_approve) instead of the always-allow default.

Requires ANTHROPIC_API_KEY (or GEMINI_API_KEY, see below) to be set in the
environment, or in a .env file in the current directory (loaded here — the
provider SDKs only read real process environment variables, never a .env
file on their own).

Provider selection: defaults to Anthropic, unchanged from before Gemini
support existed. Set MODEL_PROVIDER=gemini to use GeminiClient instead —
both satisfy the same SendsMessages Protocol, so nothing else here changes.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from bacteria.model.client import ModelClient
from bacteria.model.gemini_client import GeminiClient
from bacteria.runtime.runtime import Runtime, SendsMessages
from bacteria.session.store import SessionStore
from bacteria.tools.approval import cli_approve
from bacteria.tools.notes import build_add_note_tool
from bacteria.tools.registry import ToolRegistry


def _build_model_client() -> SendsMessages:
    provider = os.getenv("MODEL_PROVIDER", "anthropic").strip().lower()
    if provider == "gemini":
        return GeminiClient()
    return ModelClient()


def main() -> None:
    load_dotenv()
    model_client = _build_model_client()
    session_store = SessionStore()
    runtime = Runtime(model_client=model_client, session_store=session_store)

    tool_registry = ToolRegistry()
    tool_registry.register(build_add_note_tool())

    session = session_store.create_session(user_id="local-cli")
    print(f"session: {session.session_id}  (empty line or Ctrl+C to quit)")

    while True:
        try:
            user_text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_text:
            break

        result = runtime.run_turn(
            session.session_id,
            user_text,
            tool_registry=tool_registry,
            approve=cli_approve,
        )
        print(result.response.text)


if __name__ == "__main__":
    main()
