"""Asking both retrieval strategies what a past turn should have been shown.

The instrument for ADR 0006's kill criterion, and only the instrument. It
produces evidence and reaches no verdict, because the verdict needs a judgment
this module is deliberately not allowed to make — see below.

```
recorded run → the message it answered → graph traversal   ┐
                                       → what it was shown ┘ → a comparison
```

**Read as of the run, never as of now.** Every read here is bounded by the
moment the run was recorded, which is the one job §3 of the model gives recorded
time: *"evaluating a past run means reconstructing the memory that run saw"*.
Reading current beliefs instead would score yesterday's turn against facts
confirmed since, which flatters every strategy by the same unknown amount and
settles nothing. :func:`~bacteria.app.graph.service.claims_for` takes ``as_of``
for exactly this caller.

**No verdict, and the reason is not modesty.** Deciding *which set was better*
needs a label — what this turn actually needed — and there are only three ways
to get one. A model judging is refused by :mod:`bacteria.app.evaluation.checks`
on its own terms: asking a model to opine on a fact you can assert is how a
check becomes an opinion. A human judging is right and belongs in a file, not
here. And a mechanical proxy is **circular**: traversal anchors on the message,
so any label derived from the anchor is one traversal was guaranteed to hit. The
third is the dangerous one, because it would produce a number, and a number
would be believed.

Not built:
    The label, and the check over it. A CLI showing a message beside both sets
    and recording which held what the turn needed, and a check in
    :mod:`bacteria.app.evaluation.checks` scoring hit rates across the labelled
    set. Both wait on volume rather than on design: a personal graph of a few
    dozen claims and a handful of runs would produce a verdict on the project's
    central bet from a sample that cannot support one, and a noisy verdict is
    worse than none because it is citable.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.evaluation.runs import RecordedRun
from bacteria.app.personal.graph_candidates import GraphCandidateSupplier
from bacteria.app.personal.models import ChatTranscriptItem


@dataclass(frozen=True)
class Replay:
    """One run, with what it saw beside what the graph would have offered.

    Attributes:
        run_id: The run this replays. Selects the evidence it came from.
        message: The user text that turn answered, or ``None`` when the run's
            slice holds no user message — which happens and is not an error.
        shown: The memory keys the turn was actually given, from ``run_meta``.
        traversal: What :class:`GraphCandidateSupplier` returns for that message
            against the graph as believed then, as rendered statements.
        considered: How many confirmed claims existed at that moment. The
            denominator, and it is reported for the same reason ADR 0022 makes
            suppliers report it: a strategy that narrows from four is not
            evidence about a strategy that narrows from four hundred.
        gradable: Whether this run can be scored at all. False for runs recorded
            before the runtime wrote memory keys — counting those as misses
            would blame a strategy for the instrumentation.
    """

    run_id: str
    message: Optional[str]
    shown: list[str]
    traversal: list[str]
    considered: int
    gradable: bool


async def replay(
    db: AsyncSession,
    runs: Sequence[RecordedRun],
    *,
    user_id: str,
    limit: int = 8,
) -> list[Replay]:
    """Re-ask the graph what each of these runs was about.

    ``limit`` is the candidate bound the supplier is given, and it should match
    what the runtime uses in production: a comparison run at a different bound is
    measuring the bound.

    Runs are replayed independently and in order. Nothing is written.
    """
    out: list[Replay] = []
    for run in runs:
        moment = await _run_recorded_at(db, run.run_id)
        message = await _user_message(db, run.run_id)

        statements: list[str] = []
        considered = 0
        if message is not None and moment is not None:
            supplier = GraphCandidateSupplier(db, user_id, as_of=moment)
            found = await supplier.candidates(run.session_id, message, limit)
            statements = sorted(entry.value for entry in found.user.values())
            considered = found.considered

        out.append(
            Replay(
                run_id=run.run_id,
                message=message,
                shown=run.memory_keys,
                traversal=statements,
                considered=considered,
                gradable=run.gradable,
            )
        )
    return out


async def _user_message(db: AsyncSession, run_id: str) -> Optional[str]:
    """The user text this run answered.

    The first user message in the run's slice, not the last: a run holds one
    incoming turn, and anything later in the slice was written by the agent.
    """
    rows = await db.exec(
        select(ChatTranscriptItem)
        .where(col(ChatTranscriptItem.run_id) == run_id)
        .order_by(col(ChatTranscriptItem.seq))
    )
    for row in rows.all():
        payload = row.payload or {}
        if row.kind == "message" and payload.get("role") == "user":
            text = payload.get("text")
            return text if isinstance(text, str) else None
    return None


async def _run_recorded_at(db: AsyncSession, run_id: str) -> Optional[datetime]:
    """When this run happened, as the graph's clock would have seen it.

    The first transcript item's timestamp rather than the last. A turn's memory
    is assembled before the model is called, so the beliefs it saw are the ones
    held at the *start* of the run — using the end would include anything the
    turn's own extraction wrote, which is the memory it produced rather than the
    memory it used.
    """
    rows = await db.exec(
        select(ChatTranscriptItem)
        .where(col(ChatTranscriptItem.run_id) == run_id)
        .order_by(col(ChatTranscriptItem.seq))
        .limit(1)
    )
    row = rows.first()
    return row.timestamp if row is not None else None
