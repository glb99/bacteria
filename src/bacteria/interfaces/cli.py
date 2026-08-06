"""Where work enters the system: a terminal read-eval loop.

An interface's job is narrow — receive an event from outside and hand it to the
runtime. It holds no conversation logic, no prompting, and no tool behavior, so
adding a second interface (HTTP, a bot, a scheduled job) means writing another
module this thin rather than untangling this one.

It does own **composition**, though, and that is deliberate. Nothing else in the
system decides which model provider to use, which tools this deployment has, or
who approves a call — those are deployment questions, not library questions, and
answering them here keeps every other module free of global configuration. This
is the only file that constructs concrete implementations; everything below it
receives what it needs as an argument.

Credentials are read from the process environment, with ``.env`` loaded into it
first. Provider SDKs read real environment variables and never a ``.env`` file
on their own, so without that call a configured key looks, from inside the SDK,
exactly like no key at all.

Not built:
    Session continuity. Each invocation creates a fresh session, so nothing is
    remembered between runs of the command. This is a consequence of the store
    being in-memory, not an interface decision — see
    :mod:`bacteria.session.store`.

    Per-run tool scoping. Every registered tool is exposed on every turn. The
    registry supports narrowing; there is no policy here to narrow by.

    Argument parsing. No flags, no subcommands, no ``--provider``. Environment
    variables are the entire configuration surface. A real CLI would use
    ``argparse`` here and keep the environment as the fallback.
"""

from __future__ import annotations

import os
from typing import Callable

from dotenv import load_dotenv

from bacteria.model.client import ModelClient
from bacteria.model.gemini_client import GeminiClient
from bacteria.model.protocol import SendsMessages
from bacteria.runtime.runtime import Runtime
from bacteria.session.store import SessionStore
from bacteria.tools.approval import cli_approve
from bacteria.tools.notes import build_add_note_tool
from bacteria.tools.registry import ToolRegistry

PROVIDERS: dict[str, Callable[[], SendsMessages]] = {
    "anthropic": ModelClient,
    "gemini": GeminiClient,
}
"""Selectable model providers, keyed by ``MODEL_PROVIDER``.

A table rather than a chain of conditionals: adding a provider is one entry,
and the set of valid values is readable at a glance instead of inferred from
control flow. Each entry needs its own API key in the environment.

Typed as a zero-argument factory rather than a class, because that is all this
module requires — a provider needing constructor arguments can be added as a
``lambda`` without changing the table's type.
"""

DEFAULT_PROVIDER = "anthropic"


def build_model_client(provider: str | None = None) -> SendsMessages:
    """Construct the configured model client.

    Args:
        provider: Overrides ``MODEL_PROVIDER``. Mostly for tests.

    Returns:
        A client satisfying the protocol. Which concrete class it is stops
        mattering the moment it is returned.

    Raises:
        ValueError: Unrecognized provider name. Rejected rather than silently
            falling back to the default — a typo in ``MODEL_PROVIDER`` should
            not quietly bill a different vendor.
        CredentialsError: The chosen provider found no usable API key. Some
            providers surface this at construction, others on the first call.
    """
    name = (provider or os.getenv("MODEL_PROVIDER", DEFAULT_PROVIDER)).strip().lower()
    try:
        client_cls = PROVIDERS[name]
    except KeyError:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"unknown MODEL_PROVIDER {name!r}; expected one of: {known}") from None
    return client_cls()


def build_tool_registry() -> ToolRegistry:
    """Declare what this deployment can do.

    The complete capability surface, in one readable list. A tool that is not
    registered here does not exist as far as the model is concerned, which is
    the property that makes this function worth having separately.
    """
    registry = ToolRegistry()
    registry.register(build_add_note_tool())
    return registry


def main() -> None:
    """Run the interactive loop until the user exits.

    Exits on an empty line, EOF, or interrupt. Exceptions from a turn are not
    caught: a failed turn should be visible, and its evidence is already
    committed to the session by the runtime before the exception reaches here.
    """
    load_dotenv()

    session_store = SessionStore()
    runtime = Runtime(model_client=build_model_client(), session_store=session_store)
    tool_registry = build_tool_registry()

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
            # The real gate. Omitting it would leave the permissive default in
            # place, which is wrong the moment a human is watching.
            approve=cli_approve,
        )
        print(result.response.text)


if __name__ == "__main__":
    main()
