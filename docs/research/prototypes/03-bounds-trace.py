"""Prototype 03 — the same trace, with E3's three-state bounds.

[`02-executable-trace.py`](02-executable-trace.py) found that everything
involving valid-time overlap depended on a reading of `[?..]` that the model
never chose, and it is kept unchanged as the record of that finding. This file
implements the proposed fix from [E3](../dialogues/04-executable-findings.md) and
re-runs the trace to see what survives.

The fix: an end bound has three states, not two.

    known      ended on date X            "she left in February"
    OPEN       has not ended; true now    "she's their CTO"
    UNKNOWN    may or may not have ended  "she was mentioned as CTO"

Starts have two (known, UNKNOWN). In Postgres this is `'infinity'` for OPEN,
NULL for UNKNOWN, and a date for known — no extra column, and NULL keeps its
real SQL meaning.

The consequence that matters: OPEN means *true as of now*, so an open-ended
interval provably contains the present moment, and **two open-ended intervals
definitely overlap** however unknown their starts are. That is what lets the
week-3 contradiction fire honestly rather than by claiming Diane was CTO since
the beginning of time.

Overlap is three-valued throughout, which is no longer a policy choice: with
UNKNOWN as a distinct state, "undecided" is simply what the comparison returns.

Run: `python 03-bounds-trace.py`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional, Union

W1 = date(2026, 5, 4)
W2 = date(2026, 5, 11)
W3 = date(2026, 5, 18)
W4 = date(2026, 5, 25)
FEB = date(2026, 2, 15)


class Bound(Enum):
    OPEN = "open"  # 'infinity' — true as of now, not ended
    UNKNOWN = "unknown"  # NULL — no information


Endpoint = Union[date, Bound]
OPEN, UNKNOWN = Bound.OPEN, Bound.UNKNOWN


@dataclass(frozen=True)
class Interval:
    start: Endpoint = UNKNOWN
    end: Endpoint = UNKNOWN

    def __str__(self) -> str:
        def fmt(b: Endpoint) -> str:
            return {OPEN: "open", UNKNOWN: "?"}.get(b, str(b))

        return f"[{fmt(self.start)}..{fmt(self.end)}]"


def overlaps(a: Interval, b: Interval) -> Optional[bool]:
    """Three-valued: True, False, or None for 'cannot be determined'.

    Not a policy any more. UNKNOWN is a distinct state, so undecided is simply
    what the comparison returns when the unknowns could change the answer.
    """
    # Both still running: they share the present moment, whatever their starts.
    if a.end is OPEN and b.end is OPEN:
        return True

    def apart(x: Interval, y: Interval) -> bool:
        """x ends at or before y starts, provably."""
        if x.end is OPEN or x.end is UNKNOWN:
            return False
        if not isinstance(y.start, date):
            return False
        return x.end <= y.start

    if apart(a, b) or apart(b, a):
        return False

    # Determined only when nothing unknown remains.
    if UNKNOWN in (a.start, a.end, b.start, b.end):
        return None
    return True


@dataclass
class Assertion:
    id: str
    subject: str
    predicate: str
    object: str
    valid: Interval
    recorded_at: date
    recorded_until: Optional[date] = None
    source: str = "conversation"
    actor: str = "agent"
    inferred: bool = False

    def believed_at(self, t: date) -> bool:
        return self.recorded_at <= t and (
            self.recorded_until is None or self.recorded_until > t
        )


@dataclass
class Conclusion:
    id: str
    statement: str
    evidence: list[str]
    confidence: float
    status: str = "active"


@dataclass
class Log:
    assertions: list[Assertion] = field(default_factory=list)
    conclusions: list[Conclusion] = field(default_factory=list)

    def append(self, a: Assertion) -> Assertion:
        self.assertions.append(a)
        return a

    def by_id(self, aid: str) -> Assertion:
        return next(a for a in self.assertions if a.id == aid)

    def state_at(self, t: date) -> list[Assertion]:
        return [a for a in self.assertions if a.believed_at(t)]

    def supersede(self, aid: str, new_id: str, new_valid: Interval,
                  at: date, actor: str = "user") -> Assertion:
        old = self.by_id(aid)
        old.recorded_until = at
        for c in self.conclusions:
            if aid in c.evidence and c.status == "active":
                c.status = "stale"
        return self.append(
            Assertion(new_id, old.subject, old.predicate, old.object,
                      new_valid, at, source=old.source, actor=actor)
        )


ACME, CTO = "org:acme", "cto"
Conflict = tuple[str, str, Optional[bool]]


def functional_conflicts(log: Log, at: date, policy_infer: bool) -> list[Conflict]:
    live = [
        a for a in log.state_at(at)
        if a.subject == ACME and a.predicate == CTO
    ]
    if policy_infer:
        live = _infer_successor_starts(live)

    out: list[Conflict] = []
    for i, a in enumerate(live):
        for b in live[i + 1:]:
            if a.object == b.object:
                continue
            v = overlaps(a.valid, b.valid)
            if v is not False:
                out.append((a.id, b.id, v))
    return out


def _infer_successor_starts(live: list[Assertion]) -> list[Assertion]:
    """E1: assume the successor began when the predecessor ended.

    An assumption, not an observation — there may have been a gap with no CTO.
    Per §5 that makes it a conclusion carrying evidence, not a derivation.
    """
    ends = [a.valid.end for a in live if isinstance(a.valid.end, date)]
    if not ends:
        return live
    latest = max(ends)
    out = []
    for a in live:
        if a.valid.start is UNKNOWN and a.valid.end is OPEN:
            out.append(
                Assertion(**{**a.__dict__,
                             "valid": Interval(latest, OPEN),
                             "inferred": True})
            )
        else:
            out.append(a)
    return out


def build_log() -> Log:
    log = Log()
    # Week 1. "She's their CTO" is present tense -> the end is OPEN, not unknown.
    log.append(Assertion("a1", "person:diane", "isa", "Person", Interval(), W1))
    log.append(Assertion("a2", ACME, "isa", "Organization", Interval(), W1))
    log.append(Assertion("a3", ACME, CTO, "person:diane", Interval(UNKNOWN, OPEN), W1))
    log.append(Assertion("a4", "event:coffee", "topic", "integration",
                         Interval(W1, W1), W1))

    # Week 2.
    log.append(Assertion("a5", "person:diana", "email", "diana@acme.com",
                         Interval(), W2, source="email"))
    log.append(Assertion("a6", "person:diane", "sameAs", "person:diana",
                         Interval(), W2, actor="user"))
    log.conclusions.append(
        Conclusion("c1", "Diane is the decision-maker for the Acme integration",
                   ["a3", "a4", "a5"], 0.72)
    )

    # Week 3. Also present tense.
    log.append(Assertion("a7", ACME, CTO, "person:bob", Interval(UNKNOWN, OPEN),
                         W3, source="newsletter"))

    # Week 4. Append-only: a3's recorded interval closes, a8 states the same
    # fact with a known end.
    log.supersede("a3", "a8", Interval(UNKNOWN, FEB), at=W4)
    return log


def verdict(cs: list[Conflict]) -> str:
    if not cs:
        return "none"
    return "conflict" if cs[0][2] is True else "undecided"


def main() -> None:
    print("Prototype 03 - three-state bounds (E3)\n")
    for infer in (False, True):
        log = build_log()
        w3 = verdict(functional_conflicts(log, W3, infer))
        w4 = verdict(functional_conflicts(log, W4, infer))
        c1 = log.conclusions[0].status
        believed = {a.id for a in log.state_at(W2)}
        w2_ok = "a3" in believed and "a8" not in believed
        print(f"  infer={str(infer):5}  W3={w3:10} W4={w4:10} "
              f"c1={c1:6} state_at(W2)={'ok' if w2_ok else 'WRONG'}")

    print("\n  W3 fires as a real conflict, not by claiming Diane was CTO")
    print("  since the beginning of time: two OPEN ends share the present.")
    print("  W4 stays undecided without the E1 inference - Bob's start is")
    print("  still unknown, so nothing proves the two roles apart.")


if __name__ == "__main__":
    main()
