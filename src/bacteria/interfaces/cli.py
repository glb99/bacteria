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

Requires ANTHROPIC_API_KEY to be set in the environment.
"""

from __future__ import annotations

from bacteria.model.client import ModelClient
from bacteria.runtime.runtime import Runtime
from bacteria.session.store import SessionStore


def main() -> None:
    model_client = ModelClient()
    session_store = SessionStore()
    runtime = Runtime(model_client=model_client, session_store=session_store)

    session = session_store.create_session(user_id="local-cli")
    print(f"session: {session.session_id}  (empty line or Ctrl+C to quit)")

    while True:
        try:
            user_text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_text:
            break

        result = runtime.run_turn(session.session_id, user_text)
        print(result.response.text)


if __name__ == "__main__":
    main()
