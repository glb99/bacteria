"""Choosing what the model is told, by asking the graph what this message is about.

The implementation of the agent's ``SuppliesMemoryCandidates``, and the last
piece of the bet ADR 0006 made. Everything before it was building the substrate;
this is the part that has to earn it.

```
message → anchor resolution → one hop → confirmed claims → MemoryEntry values
```

**Anchor resolution is exact then lexical, and there are no vectors.** ADR 0006
orders it *exact identifier → lexical/alias → vector*, and stopping after the
second is deliberate rather than unfinished: embeddings cost money and a
migration, and the question they would improve — *does traversal beat recency* —
can be asked without them. If a lexical anchor plus one hop cannot beat recency
on a personal graph of a few dozen nodes, better anchoring is unlikely to rescue
it; if it can, vectors make it better rather than make it work.

**Only confirmed claims are returned.** That is not this module's rule to relax:
:func:`~bacteria.app.graph.service.claims_for` filters ``origin == "stated"`` and
is one of exactly two functions permitted to decide what may be spoken. An index
ranks; it does not speak.

Not built:
    Vectors, per above — both the entity-linking kind and the semantic-retrieval
    kind ADR 0006 distinguishes.

    More than one hop. A second hop multiplies the candidate set by the branching
    factor and needs a reason; the first version should be able to fail cleanly,
    and a bounded thing that fails is more informative than an unbounded one that
    does.
"""

from datetime import datetime
from typing import Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.agent.context.retrieval import Candidates
from bacteria.agent.session.store import MemoryEntry
from bacteria.app.graph.identity import normalize
from bacteria.app.graph.repository import SqlGraphRepository
from bacteria.app.graph.service import claims_for

_MIN_ANCHOR_CHARS = 3
"""How short a label may be and still be looked for in a message.

Two characters match constantly — "my", "in", an initial — and an anchor that
matches everything narrows nothing while costing a hop. Names shorter than this
exist and are lost; that is under-claiming, which is the recoverable direction
everywhere else in this package.
"""


class GraphCandidateSupplier:
    """Narrowing, backed by the graph.

    Takes the session it should read through and the owner whose graph it is.
    Both are fixed for the life of the supplier, because a supplier answers for
    one person and a caller that could change that mid-turn is a caller that
    could show one person another's memory.
    """

    def __init__(
        self, session: AsyncSession, user_id: str, *, as_of: Optional[datetime] = None
    ) -> None:
        self._db = session
        self._user_id = user_id
        self._as_of = as_of
        """The moment whose beliefs to read, or ``None`` for now.

        Set only when replaying a past run, and set on the supplier rather than
        passed to :meth:`candidates` because that signature is the agent's
        ``SuppliesMemoryCandidates`` protocol — a host adding an argument to it
        would be a host deciding the protocol.

        It also cannot vary within one supplier's life, which is the same
        argument ``user_id`` makes: a caller able to change *when* mid-turn could
        show a person a memory the turn did not have.
        """

    async def candidates(self, session_id: str, user_text: str, limit: int) -> Candidates:
        """The confirmed claims this message appears to be about.

        ``considered`` counts everything confirmed, not everything returned. A
        supplier that read forty and handed back four must say forty, or a
        memory the owner deliberately kept stops reaching the model with nothing
        recording that it had — ADR 0022's invariant, which does not survive by
        accident.

        Returned in the ``user`` scope, always. A confirmed fact is about the
        person's world rather than about one conversation, and putting it in the
        session scope would make it win precedence over a preference stated in
        this very conversation — which is exactly backwards.
        """
        repository = SqlGraphRepository(self._db)
        everything = await claims_for(repository, self._user_id, as_of=self._as_of)
        if not everything:
            return Candidates(considered=0)

        anchors = await self._anchors(repository, user_text)
        # No anchor means no opinion, and an opinion is what this exists to have.
        # Returning everything would make the supplier a slower way of doing what
        # assembly already did, and returning nothing would hide memories a
        # person kept behind a message that happened to name nobody.
        chosen = (
            everything
            if not anchors
            else await claims_for(repository, self._user_id, anchors=anchors, as_of=self._as_of)
        )

        entries = {
            claim.assertion_id: MemoryEntry(
                value=claim.statement,
                reason=claim.reason,
                # The graph is the proposer of record here. `source` says who
                # suggested a memory, and every one of these was confirmed by the
                # owner but *found* by traversal.
                source="graph",
            )
            for claim in chosen[:limit]
        }
        return Candidates(user=entries, considered=len(everything))

    async def _anchors(self, repository: SqlGraphRepository, user_text: str) -> list[str]:
        """Which known things this message names.

        Substring matching over normalized labels, which is the lexical half of
        ADR 0006's ordering. Crude, and its crudeness is bounded by the same rule
        identity resolution uses: it can only *fail to find* a node, never
        conflate two, because a match is exact on the label rather than similar
        to it.
        """
        haystack = normalize(user_text)
        found: list[str] = []
        for node in await repository.nodes(self._user_id):
            label = normalize(node.label)
            if len(label) >= _MIN_ANCHOR_CHARS and label in haystack:
                found.append(node.node_id)
        return found
