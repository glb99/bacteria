"""Where work enters the system: a terminal read-eval loop.

An interface's job is narrow — receive an event from outside and hand it to the
runtime. It holds no conversation logic, no prompting, and no tool behavior, so
adding a second interface (HTTP, a bot, a scheduled job) means writing another
module this thin rather than untangling this one.

Concrete implementations are chosen in :mod:`app.composition`. This loop creates
the in-memory session store, because that store belongs to this surface, and
passes the composed model, tools, and retriever into ``run_turn``.

Credentials are read from the process environment, with ``.env`` loaded into it
first. Provider SDKs read real environment variables and never a ``.env`` file
on their own, so without that call a configured key looks, from inside the SDK,
exactly like no key at all.

Not built:
    Session continuity. Each invocation creates a fresh session, so nothing is
    remembered between runs of the command. This is a consequence of the store
    being in-memory, not an interface decision — see
    :mod:`bacteria.agent.session.store`.

    Per-run tool scoping. Every registered tool is exposed on every turn. The
    registry supports narrowing; there is no policy here to narrow by.

    Argument parsing. No flags, no subcommands, no ``--provider``. Environment
    variables are the entire configuration surface. A real CLI would use
    ``argparse`` here and keep the environment as the fallback.
"""

from __future__ import annotations

import anyio
from dotenv import load_dotenv

from app.agent.runtime import run_turn
from app.agent.session import InMemorySessionRepository
from app.composition import (
    build_embedding_page_retriever,
    build_model_client,
    build_tool_registry,
)
from app.observability import get_tracer, setup_observability


async def _run() -> None:
    """Run the interactive loop until the user exits.

    Exits on an empty line, EOF, or interrupt. Exceptions from a turn are not
    caught: a failed turn should be visible, and its evidence is already
    committed to the session by the runtime before the exception reaches here.
    """
    load_dotenv()
    session_repository = InMemorySessionRepository()
    session = session_repository.create_session()
    document_retriever = build_embedding_page_retriever()
    print(f"session: {session.session_id}  (empty line or Ctrl+C to quit)")

    while True:
        try:
            # Blocking `input` on the event loop, knowingly. This process runs
            # one turn at a time and has nothing else to schedule, so there is
            # no concurrency for it to stall. A surface that serves more than
            # one caller must not read its input this way.
            user_text = input("> ").strip()

        except (EOFError, KeyboardInterrupt):
            break
        if not user_text:
            break

        with get_tracer().start_as_current_span("agent.run_turn") as span:
            span.set_attribute("session.id", session.session_id)
            span.set_attribute("input.text", user_text)
            result = await run_turn(
                session_id=session.session_id,
                user_text=user_text,
                model_client=build_model_client(),
                tool_registry=build_tool_registry(),
                session_repository=session_repository,
                document_retriever=document_retriever,
            )
            span.set_attribute("run.id", result.run_id)

        print(result.response.text)


def main() -> None:
    """Console-script entry point: start an event loop and hand off to :func:`_run`.

    The loop is started *here*, at the outermost edge, and nowhere else. A
    library that starts its own loop cannot be embedded in a process that
    already has one — which is the entire situation this agent is heading into.
    """
    # Document rows are loaded through a synchronous engine in ``_run``.
    # psycopg's async mode cannot use Windows' ProactorEventLoop, so a
    # Postgres-backed session store that queried asynchronously would still
    # fail at its first query here. The host application chooses its loop in
    # its own entrypoints for that reason.
    setup_observability()  # TODO: maybe is it better to have a Hynek's style entrypoint setup
    anyio.run(_run)


if __name__ == "__main__":
    main()
