"""Agreeing, and disagreeing, with what the codebase suggests about itself.

The first thing this feature writes down. Everything else is re-read from the
files on every request, because a parse is repeatable and storing it would be a
cache pretending to be a record. **A decision is not repeatable.** Nobody can
re-derive that you looked at *"chat is a feature"* on a Tuesday and said no, so
the row is the only evidence and the log is exactly what it is for.

**Disagreement is recorded, never deleted.** Rejecting appends ``is_not_a``
rather than dropping the proposal, matching what the graph already does for a
refused merge -- confirming appends ``same_as``, rejecting appends
``distinct_from``. A rejection that merely disappears leaves the same regularity
re-proposing the same claim forever, which is how a review queue becomes a thing
people stop reading.

**Its own ontology, per project.** The rows live beside a person's memory and
never inside it: the repository is opened on ``architecture:<project id>`` and
every read and write is filtered to it. `user_id` still answers *whose*, the
ontology answers *which model*, and ``stated_by`` answers *who said so* -- which
is the question a shared architecture asks first and a personal graph never had
to.

Not built:
    Constraints. Nothing here can contradict anything else yet: a package could
    be agreed a feature and a layer at once and no rule would object. The
    machinery exists and this domain has not earned a rule, which is a better
    reason to leave it out than that it would be hard.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, Optional

from bacteria.app.architecture.catalogue import KIND, PACKAGE, WORD
from bacteria.app.architecture.models import Project
from bacteria.app.graph.log import Assertion
from bacteria.app.graph.repository import SqlGraphRepository
from bacteria.app.graph.service import refer_to
from bacteria.app.graph.temporal import OPEN_ENDED, Interval

Verdict = Literal["agreed", "disagreed"]

AGREE = "is_a"
DISAGREE = "is_not_a"


def ontology_of(project: Project) -> str:
    """The partition this project's model lives in.

    Prefixed rather than the bare id so that a row is legible in a database
    somebody is reading by hand. Every question about these rows starts with
    "which of these are architecture", and an opaque uuid answers it badly.
    """
    return f"architecture:{project.project_id}"


@dataclass(frozen=True)
class Decision:
    """One judgment a person made about one proposal."""

    subject: str
    claim: str
    verdict: Verdict
    stated_by: Optional[str]
    at: datetime


def _decision_id(ontology: str, subject: str, claim: str, now: datetime) -> str:
    """Deterministic, so the same judgment made twice in one instant is one row.

    The same reasoning the extractor's ids use: a retried request must land
    where it did rather than raise, and a random id would defeat the unique
    constraint by never colliding.
    """
    material = f"{ontology}\x00{subject}\x00{claim}\x00{now.isoformat()}"
    return hashlib.sha256(material.encode()).hexdigest()[:32]


async def decide(
    repository: SqlGraphRepository,
    *,
    project: Project,
    subject: str,
    claim: str,
    verdict: Verdict,
    stated_by: str,
    now: datetime,
) -> Decision:
    """Record that somebody agreed or disagreed with a proposed classification.

    **Changing your mind closes the old row rather than editing it.** A person
    who agrees today and disagrees next month has said two things at two times,
    and the log is meant to be able to answer what they believed in between.
    """
    ontology = ontology_of(project)
    owner = project.principal_id

    subject_node = await refer_to(
        repository, owner, PACKAGE if claim != "role" else WORD, subject, now=now
    )
    claim_node = await refer_to(repository, owner, KIND, claim, now=now)
    relation = AGREE if verdict == "agreed" else DISAGREE

    for existing in await _about(repository, owner, subject_node.node_id, claim_node.node_id):
        if existing.rel == relation:
            # The same judgment restated. Rewriting it would move its date and
            # lose when it was actually made.
            return _decision(existing, subject, claim)
        # Stamped before closing, because `close` copies the timestamp off the
        # assertion it is handed rather than setting one. Passing the row back
        # unchanged assigns `recorded_until = None` over `None` and returns
        # quietly, which left every reversal in this database standing beside
        # the judgment it was meant to replace -- `is_a` and `is_not_a` both
        # current, and whichever the reader happened to see last winning.
        await repository.close(replace(existing, recorded_until=now, closed_by="superseded"))

    claim_row = Assertion(
        assertion_id=_decision_id(ontology, subject, claim, now),
        user_id=owner,
        src=subject_node.node_id,
        rel=relation,
        dst=claim_node.node_id,
        valid=Interval(start=None, end=OPEN_ENDED),
        recorded_at=now,
        # A person said it, which is what makes it speakable and what separates
        # it from everything else this feature produces.
        origin="stated",
        trust="user",
        stated_by=stated_by,
        attrs={"subject": subject, "claim": claim},
    )
    await repository.record([claim_row])
    return _decision(claim_row, subject, claim)


async def decisions(repository: SqlGraphRepository, *, project: Project) -> tuple[Decision, ...]:
    """Every judgment still standing for this project.

    Read from the log rather than a projection, so a decision retracted through
    any route disappears from here without this module being told.
    """
    labels = {node.node_id: node.label for node in await repository.nodes(project.principal_id)}
    believed = await repository.current(project.principal_id)
    return tuple(
        _decision(
            claim,
            claim.attrs.get("subject", labels.get(claim.src, claim.src))
            if claim.attrs
            else labels.get(claim.src, claim.src),
            claim.attrs.get("claim", labels.get(claim.dst, claim.dst))
            if claim.attrs
            else labels.get(claim.dst, claim.dst),
        )
        for claim in believed
        if claim.rel in (AGREE, DISAGREE)
    )


def _decision(claim: Assertion, subject: str, name: str) -> Decision:
    return Decision(
        subject=subject,
        claim=name,
        verdict="agreed" if claim.rel == AGREE else "disagreed",
        stated_by=claim.stated_by,
        at=claim.recorded_at,
    )


async def _about(
    repository: SqlGraphRepository, owner: str, src: str, dst: str
) -> Sequence[Assertion]:
    return [
        claim
        for claim in await repository.current(owner)
        if claim.src == src and claim.dst == dst and claim.rel in (AGREE, DISAGREE)
    ]
