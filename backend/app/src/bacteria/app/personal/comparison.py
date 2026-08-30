"""Asking both memory stores the same question, and reporting where they differ.

**This is not ADR 0006's kill criterion, and the difference matters.** That asks
whether traversal-based candidate supply beats recency on the agent's eval
harness — a question about *retrieval*, which is unbuilt. This asks a smaller and
more immediate one: for a session that exists, do the two stores hold the same
keyed memory, and if not, what is missing from which.

That is the question somebody has to answer before turning
``graph_backed_memory`` on, and it was unanswerable until both stores existed.

**Neither side is treated as correct.** The obvious shape would be to diff the
graph against the tables and call the tables right, which would make every gap in
the graph a defect and every gap in the tables invisible. They are two answers to
one question and the report says so, because the interesting finding early on is
the graph knowing *less* and the interesting finding later is it knowing
something the tables could not hold.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.personal.graph_memory import GraphMemoryStore
from bacteria.app.personal.memory import MemoryStore, TableMemoryStore


@dataclass(frozen=True)
class Divergence:
    """One key the two stores answer differently."""

    key: str
    collection: str
    tables: Any = None
    graph: Any = None

    @property
    def kind(self) -> str:
        if self.tables is not None and self.graph is None:
            return "only in tables"
        if self.graph is not None and self.tables is None:
            return "only in graph"
        return "different value"


@dataclass(frozen=True)
class Comparison:
    """What each store holds for one session, and every place they disagree."""

    session_id: str
    user_id: str
    table_keys: int = 0
    graph_keys: int = 0
    divergences: list[Divergence] = field(default_factory=list)

    @property
    def agree(self) -> bool:
        return not self.divergences


async def compare(db: AsyncSession, session_id: str, user_id: str) -> Comparison:
    """Read both stores and report the difference, changing nothing.

    Reads only. A comparison that wrote would be measuring a system it had
    already altered, and this is meant to be safe to run against a deployment
    somebody is using.
    """
    tables: MemoryStore = TableMemoryStore(db)
    graph: MemoryStore = GraphMemoryStore(db)

    from_tables = await tables.entries(session_id, user_id)
    from_graph = await graph.entries(session_id, user_id)

    divergences: list[Divergence] = []
    counted = 0
    for name in ("memory", "user_memory"):
        left = getattr(from_tables, name)
        right = getattr(from_graph, name)
        counted += len(left)
        for key in sorted(set(left) | set(right)):
            here, there = left.get(key), right.get(key)
            if here is None or there is None or here.value != there.value:
                divergences.append(
                    Divergence(
                        key=key,
                        collection=name,
                        tables=None if here is None else here.value,
                        graph=None if there is None else there.value,
                    )
                )

    # Proposals are keyed by (source, key) and the two stores key them from
    # different places -- a table row's source column against a claim's attrs --
    # so they are counted and not diffed. Reporting a mismatch there would report
    # on the bookkeeping rather than on what either store knows.
    return Comparison(
        session_id=session_id,
        user_id=user_id,
        table_keys=counted,
        graph_keys=len(from_graph.memory) + len(from_graph.user_memory),
        divergences=divergences,
    )
