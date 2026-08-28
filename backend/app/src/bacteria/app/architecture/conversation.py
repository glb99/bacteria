"""Asking a model about a codebase, with the codebase in front of it.

Composed here rather than in ``views.py`` because it decides *what the agent is
allowed to do*, which is logic and not configuration — the same reason
``chat/service.py`` sits where it does.

**A real gate, not an absent one.** ``chat/service.py`` states the rule this
module had to satisfy before it could exist: *"Adding a second tool means writing
a real gate first, not after."* The gate is
:class:`OnlyReads` — an allowlist of the read-only architecture tools that
refuses anything else, including a tool registered later by somebody who did not
read this. That is weaker than the interactive approval the CLI uses and
stronger than the auto-approver chat runs, and it is honest about which: it is
not a judgment about *this call with these arguments*, it is a judgment about
which capabilities may appear on this surface at all.

**Stateless, and the conversation lives in the browser.** Each ask opens an
in-memory session, runs one turn and discards it. Nothing is written, so nothing
has to be cleaned up, migrated, or reasoned about later — and an architecture
question is answered from the tree as it stands rather than from what was said
about it last week.

Not built:
    History. The model sees one question and the tools; it does not see what was
    asked before. Giving it that means either a table for architecture
    transcripts or trusting the client to send its own, and the second is a
    caller deciding what a model was told — which is exactly the property this
    system spends most of its design protecting. The console shows a thread
    because a person needs one; the server does not pretend to have it.
"""

from __future__ import annotations

from dataclasses import dataclass

from bacteria.agent.model.protocol import SendsMessages, ToolCall
from bacteria.agent.runtime.runtime import Runtime
from bacteria.agent.session.store import SessionStore
from bacteria.agent.tools.registry import ToolRegistry
from bacteria.app.architecture.service import Model
from bacteria.app.architecture.tools import (
    READ_ONLY,
    Verdicts,
    build_describe_package_tool,
    build_list_boundaries_tool,
    build_list_proposals_tool,
)

PREAMBLE = """You are looking at one codebase with the reader.

Answer from the tools, never from what you remember about libraries with similar
names. If a tool has not told you something, say you do not know it.

Three kinds of statement exist here and they must not be blurred:
- Derived facts — modules, imports, tables. Exact, and not worth hedging.
- Stated boundaries — rules a person wrote. They can be crossed, and they can
  also be wrong; when one is crossed, say which of the two you think it is.
- Proposals — drawn from repetition, and only ratified where someone agreed.
  Never report an open proposal as though it were settled.

You cannot change anything. Where an action is warranted — agreeing with a
proposal, accepting a crossing, running the tests — say so plainly and let the
reader do it."""


@dataclass(frozen=True)
class Answer:
    """What the model said, and what it looked at to say it.

    ``tools_used`` travels because an answer grounded in the parse and one
    invented from a plausible-sounding package name read identically, and the
    difference is the entire reason the tools exist. A reply that used no tools
    is one to distrust.
    """

    reply: str
    tools_used: tuple[str, ...]
    refused: tuple[str, ...]


class OnlyReads:
    """Allow the read-only architecture tools, refuse everything else.

    Default-deny, and that is the whole value: a tool registered later without
    being added to :data:`~bacteria.app.architecture.tools.READ_ONLY` is refused
    rather than quietly permitted. An allowlist fails closed; a denylist of the
    things somebody thought of fails open, and this design argues against
    denylists everywhere else.

    It does not ask whether *this* call with *these* arguments should run, which
    is what an approval gate is properly for. There is nobody to ask over HTTP —
    the request that would answer arrives after the one that asked — so the
    question it can answer honestly is the narrower one: may this capability
    appear on this surface at all.

    It also records what it was asked about, because nothing else can. A
    ``RunResult`` carries the *final* response, whose ``tool_calls`` are empty by
    construction once the tool round has happened — so the gate is the only
    place that sees every proposal, including the ones it refused.
    """

    def __init__(self) -> None:
        self.allowed: list[str] = []
        self.refused: list[str] = []

    def __call__(self, tool_call: ToolCall) -> bool:
        name = tool_call["name"]
        if name in READ_ONLY:
            self.allowed.append(name)
            return True
        self.refused.append(name)
        return False


def registry_for(model: Model, verdicts: Verdicts | None = None) -> ToolRegistry:
    """The tools for one project's model.

    Built per request and closed over the parse that request performed, so a
    tool cannot answer about a codebase the caller did not ask about — the same
    shape as ``remember`` being bound to the session it proposes into.
    """
    registry = ToolRegistry()
    registry.register(build_describe_package_tool(model, verdicts))
    registry.register(build_list_boundaries_tool(model))
    registry.register(build_list_proposals_tool(model, verdicts))
    return registry


ASKED = """

The reader asks: """
"""Separates the standing instructions from this turn's question.

A literal with real newlines rather than an escaped one, because writing it as
"\n\n" through a generator has silently produced an unterminated string three
times in this file's short history.
"""


async def ask(
    client: SendsMessages, model: Model, question: str, verdicts: Verdicts | None = None
) -> Answer:
    """Run one turn about one codebase."""
    store = SessionStore()
    session = await store.create_session(model.project.principal_id)
    runtime = Runtime(model_client=client, session_store=store)
    gate = OnlyReads()

    result = await runtime.run_turn(
        session_id=session.session_id,
        user_text=PREAMBLE + ASKED + question,
        tool_registry=registry_for(model, verdicts),
        approve=gate,
    )
    return Answer(
        # `text` is None when a model replied with tool calls and nothing else,
        # which is a real outcome rather than an error. Saying so beats an empty
        # bubble the reader takes for a failure.
        reply=result.response.text or "(the model called tools and said nothing)",
        tools_used=tuple(dict.fromkeys(gate.allowed)),
        refused=tuple(dict.fromkeys(gate.refused)),
    )
