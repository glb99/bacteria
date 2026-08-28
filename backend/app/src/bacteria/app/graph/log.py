"""What was claimed, and what we believed at a given moment.

The assertion as the rest of this package sees it — a frozen dataclass, not the
SQLModel row. That split is the same one ``chat/repository.py`` makes and it is
made for the same reason: everything below the repository works on detached
values, so nothing can hold a live handle on a database row and write through it
by accident. Here it buys a second thing, which is that the whole engine —
projection, constraints, inference — is testable with a list of dataclasses and
no database at all.

**Two time axes, and only one of them is about the world.** ``valid`` says when a
claim held; ``recorded_at``/``recorded_until`` say when this system believed it.
:func:`believed_at` reads the second. Reading the first instead answers a
different question — what we think *now* was true then — and the difference is
invisible until someone replays a past run and grades it against beliefs that
did not exist yet.

**Revision appends.** Nothing here edits a claim: a corrected fact is a new
assertion, and the old one's ``recorded_until`` closes. That is why
:func:`supersede` returns a pair rather than mutating, and why an assertion has
no setter for anything except the moment belief in it ended.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Iterable, Literal, Optional

from bacteria.app.graph.temporal import Interval

Closure = Literal["superseded", "retracted", "expired"]
"""Which act ended belief in a claim.

A correction and a rejection both close ``recorded_until``, and only this
says which happened. It is the difference between "we know better now" and
"a person said no", and a system that cannot tell them apart cannot report
how often its extractor is wrong.

``expired`` is the third and the one nobody performed. A tail claim nobody
ratified and nobody confirmed is closed on a clock, and it must not read as
either of the others: it is not a correction, and no person said no. Counting
it as ``retracted`` would make the extractor look wrong about facts nobody ever
looked at, which is the opposite of what happened — the word was offered as
evidence, the evidence sat there, and nothing came of it.
"""

Origin = Literal["stated", "inferred"]
"""Did anybody mean this claim, or did something work it out?

The distinction a projection needs before it may put a claim in front of a model,
and the one ``trust`` cannot make: that says which channel a claim arrived
through, which is nearly always ``third-party`` and says nothing about whether
anyone asserted it.

An extractor writes ``inferred``, always. ``stated`` is reached only by an act of
the owner's, which is what keeps *memory is written by the owner, not the model*
true of a system where the model does most of the writing.
"""

Scope = Literal["user", "session"]
"""Where a claim applies, which is not where it came from."""

Trust = Literal["user", "third-party", "inferred"]
"""Where a claim came from, which gates its *influence* and never its storage.

A claim from third-party text — a forwarded email, a fetched page, a tool result
— is stored exactly like any other and may not affect which memories are
surfaced. Nothing in any tier reaches a model unconfirmed, so this is not the
boundary that keeps unreviewed text out of a prompt; it is the one that keeps
attacker-controlled text from quietly reordering what a person already approved.

``"user"`` is deliberately not a strong claim. People paste documents into chat,
so an extractor reading a user's message is sometimes reading someone else's
text through a trusted channel, and no heuristic reliably tells those apart.
"""


@dataclass(frozen=True)
class Assertion:
    """One claim about the world, detached from the row it came from.

    ``assertion_id`` is a surrogate, and that is the difference between this and
    a current-state edge: the same ``(src, rel, dst)`` may be claimed, retracted
    and claimed again, and each of those is its own assertion with its own
    identity. Evidence links point at *this* id, so a later revision cannot
    silently rewrite the premise a past conclusion cited.

    ``recorded_until`` of ``None`` means the claim is still believed. It is the
    only field that ever changes, and it changes through :func:`supersede`.
    """

    assertion_id: str
    user_id: str
    src: str
    rel: str
    dst: str
    valid: Interval
    recorded_at: datetime
    recorded_until: Optional[datetime] = None
    closed_by: Optional[Closure] = None
    origin: Origin = "inferred"
    scope: Scope = "user"
    trust: Trust = "user"
    attrs: dict[str, Any] | None = None
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    stated_by: Optional[str] = None
    """The principal who said it, where anybody did.

    ``trust`` records how a claim arrived and ``origin`` whether anybody meant
    it; neither says *who*. That was invisible while a graph had one owner and
    is the first question anybody asks of a shared one -- and it cannot be
    added afterwards, because inventing an author for a row already written is
    the false history this log exists to prevent.
    """

    def believed_at(self, moment: datetime) -> bool:
        """Was this claim believed at ``moment``?

        Half-open on the closing side: an assertion superseded at ``T`` was still
        believed *up to* ``T`` and not at it. Without that, a revision and the
        claim it replaces both count as believed at the instant of revision, and
        every constraint sees a contradiction that lasted zero time.
        """
        if self.recorded_at > moment:
            return False
        return self.recorded_until is None or self.recorded_until > moment


def state_at(assertions: Iterable[Assertion], moment: datetime) -> list[Assertion]:
    """Everything believed at ``moment`` — the projection, folded from the log.

    This is what makes a past run reviewable: the agent's ADR 0020 replays
    recorded runs, and grading one means reconstructing the memory it actually
    saw rather than the memory we have now.
    """
    return [a for a in assertions if a.believed_at(moment)]


def current(assertions: Iterable[Assertion]) -> list[Assertion]:
    """Everything believed now, without asking for a timestamp.

    A convenience over :func:`state_at`, and worth its own name because it is the
    common case and because ``state_at(log, datetime.now(timezone.utc))`` invites
    a caller to pass a naive ``now()`` by mistake.
    """
    return [a for a in assertions if a.recorded_until is None]


def retract(old: Assertion, *, at: datetime) -> Assertion:
    """Close belief in a claim, replacing it with nothing.

    The sibling ``supersede`` named and did not write. A correction states what
    is true instead; this states only that the claim should not be believed.

    **It is a statement about belief, not about the world.** *"The extractor got
    that wrong"* closes a row; *"elena is not my mother"* is a negative fact and
    this is not it — the graph has no representation for negation, and using this
    as one would make every correction of an extraction error read as a claim
    about a person.

    Nothing is deleted. The row keeps its valid interval, its provenance and its
    evidence links, and :func:`state_at` still reconstructs the belief held
    before the correction. That is what makes a rejection recorded rather than
    absent.
    """
    return replace(old, recorded_until=at, closed_by="retracted")


def log_expire(old: Assertion, *, at: datetime) -> Assertion:
    """Close a claim because nobody ever came back to it.

    A sibling of :func:`log_retract` and deliberately not the same call. Both
    close belief and only ``closed_by`` says which happened, which is the whole
    reason that field exists.
    """
    return replace(old, recorded_until=at, closed_by="expired")


def supersede(
    old: Assertion, *, assertion_id: str, valid: Interval, at: datetime
) -> tuple[Assertion, Assertion]:
    """Revise a claim by closing belief in it and stating the corrected one.

    Returns ``(closed_old, new)``. Both are values: the caller persists them,
    and nothing has been mutated, so a failure between here and the write leaves
    the log exactly as it was.

    The new assertion keeps the old one's triple and provenance and changes only
    its valid time, because that is what a correction usually is — *she left in
    February* revises when a role ended, not who held it. A claim about a
    different triple is a new assertion, not a supersession, and callers that
    reach for this to express one are asking the wrong question.

    Its sibling is :func:`retract`, which closes belief and states nothing in its
    place. The two differ in ``closed_by`` as well as in shape, because "we know
    better now" and "a person said no" are different facts about the same row.
    """
    return (
        replace(old, recorded_until=at, closed_by="superseded"),
        replace(old, assertion_id=assertion_id, valid=valid, recorded_at=at, recorded_until=None),
    )
