"""Choosing which memories are worth saying now.

Split out of :mod:`bacteria.context.assembly` because the choice has more than
one defensible answer. Recency is the one in use; ranking against the incoming
message is the obvious other, and there are several in between. A rule with
alternatives is a policy, and a policy that lives inline as a slice expression
cannot be swapped, named, or reported on.

Nothing here does I/O. A strategy receives the candidates it may choose from and
returns a subset — which keeps it trivially testable, and is honest about the
limit: it can only rank what already fits in memory. A retriever that queries an
index instead stops being an algorithm and becomes a data-access layer, with a
different signature and a different home (the host, next to the store). That is
a migration rather than a swap, and pretending one abstraction serves both would
hide the part that actually costs something.

Scope is not visible here. :func:`~bacteria.context.assembly.assemble_context`
collapses session-scoped over user-scoped memory *before* calling a strategy, so
precedence is applied once, in the module that owns the policy, rather than
re-implemented by everything that implements this protocol. The cost is real: a
strategy cannot use scope as a ranking signal — "standing preferences outrank
conversational ones" is not expressible — and buying that back means moving
precedence in here and accepting that two implementations can then disagree
about it. See [ADR 0022](../../docs/adr/0022-memory-selection-is-a-named-strategy.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from bacteria.session.store import MemoryEntry


@dataclass(frozen=True)
class Selection:
    """What a strategy chose, and what it chose from.

    Attributes:
        chosen: The memories to render, in render order. A ``dict`` because
            insertion order is preserved and keys are what identifies a memory
            everywhere else; a list of pairs would say the same thing less
            directly.
        considered: How many were eligible before the bound was applied. This
            field is the reason this module exists as much as the protocol is.
            Assembly has always dropped the oldest entries past the limit and
            reported only how many it kept, so a memory the owner deliberately
            preserved could stop reaching the model with nothing anywhere
            recording that it had. ``considered`` minus ``len(chosen)`` is that
            number, and it reaches the transcript through ``run_meta``.
        strategy: Which rule ran. Recorded rather than inferred from
            configuration, because "which strategy was live when this turn
            happened" is a question about a past run, and configuration only
            answers it for the present one.
    """

    chosen: dict[str, MemoryEntry] = field(default_factory=dict)
    considered: int = 0
    strategy: str = ""

    @property
    def omitted(self) -> int:
        return max(self.considered - len(self.chosen), 0)


@runtime_checkable
class RetrievesMemory(Protocol):
    """A rule for picking which memories a turn should see.

    Synchronous, unlike the rest of this package's seams, and deliberately: an
    implementation that needs to await something is querying a store, which is
    the other design named in the module docstring rather than an instance of
    this one.
    """

    def select(self, query: str, limit: int, candidates: dict[str, MemoryEntry]) -> Selection:
        """Choose from ``candidates``.

        Args:
            query: The incoming user message. Unused by recency, and present
                because it is the whole input to any rule that is not recency —
                a protocol that omitted it would have to change shape the first
                time someone ranked against it.
            limit: The most that may be returned. Zero means none; a strategy
                that treats it as "no bound" inverts the strictest request into
                the loosest, which is a bug this module has already had once.
        """
        ...


class RecentMemory:
    """The most recent entries, oldest first. What this project has always done.

    Named rather than inlined so that the alternative is a substitution instead
    of an edit, and so that evidence records which rule ran. Behaviour is
    unchanged from the slice it replaces, including the ordering subtlety below.
    """

    name = "recency"

    def select(self, query: str, limit: int, candidates: dict[str, MemoryEntry]) -> Selection:
        """Keep the newest ``limit`` entries, returned oldest first.

        Sorted ascending and trimmed from the front, rather than sorted
        descending and reversed. The two differ on ties: Python's sort is
        stable, so ascending keeps entries sharing a timestamp in insertion
        order, where reversing a descending sort would flip them. Several
        memories written in one request do share a timestamp, so this is the
        ordinary case rather than a corner one — and an order that changes
        between turns is an unnecessary difference in the prompt.
        """
        if limit <= 0:
            return Selection(chosen={}, considered=len(candidates), strategy=self.name)

        oldest_first = sorted(candidates.items(), key=lambda item: item[1].created_at)
        return Selection(
            chosen=dict(oldest_first[-limit:]),
            considered=len(candidates),
            strategy=self.name,
        )
