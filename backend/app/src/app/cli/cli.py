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
    :mod:`bacteria.agent.session.store`.

    Per-run tool scoping. Every registered tool is exposed on every turn. The
    registry supports narrowing; there is no policy here to narrow by.

    Argument parsing. No flags, no subcommands, no ``--provider``. Environment
    variables are the entire configuration surface. A real CLI would use
    ``argparse`` here and keep the environment as the fallback.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import anyio
from dotenv import load_dotenv
from sqlmodel import Session, create_engine

from app.agent.model import SendsToAgent
from app.agent.retriever import (
    EmbeddingPageRetriever,
    RetrievesDocumentPages,
    StoredEntity,
)
from app.agent.runtime import run_turn
from app.agent.session import InMemorySessionRepository
from app.agent.tools import ToolRegistry, build_add_note_tool
from app.api.services.document_repository import SqlDocumentRepository
from app.llm.embeddings import GeminiEmbedder
from app.llm.multimodal import GeminiAgent
from app.observability import get_tracer, setup_observability

# The annotation is the contract this table exists to state; a checker reading
# the literal infers the two concrete classes and calls the wider declared type
# a mismatch. Widening to `dict[str, Any]` to satisfy it would delete the only
# thing here worth checking.
PROVIDERS: dict[str, Callable[[], SendsToAgent]] = {
    "gemini": GeminiAgent,
}
"""Selectable model providers, keyed by ``MODEL_PROVIDER``.

A table rather than a chain of conditionals: adding a provider is one entry,
and the set of valid values is readable at a glance instead of inferred from
control flow. Each entry needs its own API key in the environment.

Typed as a zero-argument factory rather than a class, because that is all this
module requires — a provider needing constructor arguments can be added as a
``lambda`` without changing the table's type.
"""

DEFAULT_PROVIDER = "gemini"


def build_model_client(provider: str | None = None) -> SendsToAgent:
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
    name = (provider or os.getenv("MODEL_PROVIDER",
            DEFAULT_PROVIDER)).strip().lower()
    try:
        client_cls = PROVIDERS[name]
    except KeyError:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(
            f"unknown MODEL_PROVIDER {name!r}; expected one of: {known}"
        ) from None
    return client_cls()


def build_tool_registry() -> ToolRegistry:
    """Declare what this deployment can do.

    The complete capability surface, in one readable list. A tool that is not
    registered here does not exist as far as the model is concerned, which is
    the property that makes this function worth having separately.

    Takes the store and the session because ``remember`` proposes *into* one
    conversation, so it cannot be built before there is a conversation to build
    it for. That is also why the model supplies the fact and never the session:
    the binding happens here, out of its reach.

    ``add_note`` is no longer registered. :mod:`bacteria.agent.tools.notes` is kept as
    the worked example a new tool should be modelled on, and keeping it out of
    the registry is the demonstration of what "registered" means — the module
    exists, its tests pass, and the model cannot call it.

    ``remember`` activates in the same call here, which it does on no other
    surface. The precondition is :func:`~bacteria.agent.tools.approval.cli_approve`,
    wired below: it asks the person at the keyboard, before the handler runs,
    showing them the key and the value, and they can refuse. That is the human
    ADR 0017 requires, and they are *upstream* rather than downstream.

    Without this the tool was a dead end on this surface. The model proposed,
    the user approved the call, the proposal went into a queue nothing in an
    interactive session drains, and the model reported that it had noted
    something that was never active on any later turn.
    """
    registry = ToolRegistry()
    registry.register(build_add_note_tool())
    return registry


def _psycopg_url(database_url: str) -> str:
    for scheme in ("postgres://", "postgresql://"):
        if database_url.startswith(scheme):
            return database_url.replace(scheme, "postgresql+psycopg://", 1)
    return database_url


def load_stored_entities(database_url: str) -> list[StoredEntity]:
    """Read every ``document_entity`` row into the retriever's entity list.

    The vector comes from the entity row. The image path comes from the ``page``
    row for that document and page index. A page with no row contributes an
    empty path, and ``select`` skips an empty path.
    """
    engine = create_engine(_psycopg_url(database_url))
    with Session(engine) as session:
        repository = SqlDocumentRepository(session)
        image_paths = {
            (str(page.document_id), page.page_index): page.image_path
            for page in repository.list_pages()
        }
        entities = [
            StoredEntity(
                document_id=str(row.document_id),
                page_index=row.page_index,
                vector=list(row.vector),
                image_path=image_paths.get(
                    (str(row.document_id), row.page_index), ""),
            )
            for row in repository.list_entities()
        ]
    engine.dispose()
    return entities


def build_document_retriever(
    entities: list[StoredEntity] | None = None,
    database_url: str | None = None,
) -> RetrievesDocumentPages:
    """Construct the page retriever for this deployment.

    When ``entities`` is omitted, the list is every row in ``document_entity``.
    """
    if entities is None:
        url = database_url if database_url is not None else os.environ["DATABASE_URL"]
        entities = load_stored_entities(url)
    return EmbeddingPageRetriever(embed=GeminiEmbedder(), entities=entities)


async def _run() -> None:
    """Run the interactive loop until the user exits.

    Exits on an empty line, EOF, or interrupt. Exceptions from a turn are not
    caught: a failed turn should be visible, and its evidence is already
    committed to the session by the runtime before the exception reaches here.
    """
    load_dotenv()
    session_repository = InMemorySessionRepository()
    session = session_repository.create_session()
    document_retriever = build_document_retriever()
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
