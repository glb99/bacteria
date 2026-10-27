"""Deployment wiring shared by the entry points.

This module chooses the concrete model, tools, embedder, and page retriever
for this deployment. The CLI and the HTTP dependencies call these functions.
The retriever, the runtime, and the tool implementations receive the objects
and do not choose them.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from sqlmodel import Session, create_engine

from app.agent.model import SendsToAgent
from app.agent.retriever import (
    EmbeddingPageRetriever,
    RetrievesDocumentPagesWithMetadata,
    StoredEntity,
)
from app.agent.tools import ToolRegistry, build_add_note_tool
from app.api.services.document_repository import SqlDocumentRepository
from app.llm.embeddings import Embed, GeminiEmbedder
from app.llm.multimodal import GeminiAgent

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
# Repo root is four parents up: app/ -> src/ -> backend/app/ -> backend/ -> repo.
_LOCAL_DOCUMENTS_DIR = Path(__file__).resolve().parents[4] / "documents"


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


def build_gemini_embedder() -> Embed:
    """Construct the embedder this deployment uses for labels and questions."""
    return GeminiEmbedder()


def _psycopg_url(database_url: str) -> str:
    for scheme in ("postgres://", "postgresql://"):
        if database_url.startswith(scheme):
            return database_url.replace(scheme, "postgresql+psycopg://", 1)
    return database_url


def _resolve_image_path(image_path: str) -> str:
    """Resolve container document paths to the project folder on the host."""
    container_path = PurePosixPath(image_path)
    try:
        relative_path = container_path.relative_to("/data/documents")
    except ValueError:
        return image_path

    if not relative_path.parts or ".." in relative_path.parts:
        return image_path

    if Path(image_path).is_file():
        return image_path
    return str(_LOCAL_DOCUMENTS_DIR.joinpath(*relative_path.parts))


def build_embedding_page_retriever(
    database_url: str | None = None,
) -> RetrievesDocumentPagesWithMetadata:
    """Construct the page retriever for this deployment.

    The entity list is every ``document_entity`` row. The vector comes from the
    entity row. The image path comes from the ``page`` row for that document
    and page index. Container paths are mapped to the project documents folder
    when this runs on the host. A page with no row contributes an empty path,
    and ``select`` skips an empty path.

    When ``database_url`` is omitted, the read uses the process engine from
    :mod:`app.core.db`. An explicit URL opens an engine for this call and
    closes it before returning.
    """
    owns_engine = database_url is not None
    if database_url is None:
        from app.core.db import engine
    else:
        engine = create_engine(_psycopg_url(database_url))
    try:
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
                    image_path=_resolve_image_path(
                        image_paths.get(
                            (str(row.document_id), row.page_index), ""
                        )
                    ),
                )
                for row in repository.list_entities()
            ]
    finally:
        if owns_engine:
            engine.dispose()
    return EmbeddingPageRetriever(embed=build_gemini_embedder(), entities=entities)
