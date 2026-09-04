"""Prototype 04 — constraint-driven boundary inference (E1).

[`03-bounds-trace.py`](03-bounds-trace.py) settled E3 and left week 4 *undecided*:
Diane's role ends in February, Bob's start is unknown, and nothing proves the two
apart. Clearing it requires assuming the successor began when the predecessor
ended — an assumption, not an observation.

This file implements that assumption as a **conclusion** (§6) rather than a
derivation (§5), on the grounds that the distinguishing question is not who
computed it but whether it is *entailed* or *assumed*. The data is equally
consistent with a gap, so it is assumed, so it is defeasible, so it needs
evidence links and a lifecycle.

What it checks:

    1. the undecided conflict becomes EXPLAINED, not cleared
    2. retracting the inference re-opens it, via the staleness walk
    3. inferred boundaries never feed another inference (no silent compounding)

Run: `python 04-inference-trace.py`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional, Union

W1, W2, W3, W4 = (date(2026, 5, d) for d in (4, 11, 18, 25))
FEB = date(2026, 2, 15)


class Bound(Enum):
    OPEN = "open"
    UNKNOWN = "unknown"


OPEN, UNKNOWN = Bound.OPEN, Bound.UNKNOWN
Endpoint = Union[date, Bound]


@dataclass(frozen=True)
class Interval:
    start: Endpoint = UNKNOWN
    end: Endpoint = UNKNOWN


def overlaps(a: Interval, b: Interval) -> Optional[bool]:
    if a.end is OPEN and b.end is OPEN:
        return True

    def apart(x: Interval, y: Interval) -> bool:
        return isinstance(x.end, date) and isinstance(y.start, date) and x.end <= y.start

    if apart(a, b) or apart(b, a):
        return False
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
    inferred_start: bool = False  # a boundary we assumed, not one we were told

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
    derived_by: str
    status: str = "active"  # active | stale | retracted


ACME, CTO = "org:acme", "cto"


@dataclass
class Log:
    assertions: list[Assertion] = field(default_factory=list)
    conclusions: list[Conclusion] = field(default_factory=list)

    def add(self, a: Assertion) -> Assertion:
        self.assertions.append(a)
        return a

    def state_at(self, t: date) -> list[Assertion]:
        return [a for a in self.assertions if a.believed_at(t)]

    def roles_at(self, t: date) -> list[Assertion]:
        return [
            a for a in self.state_at(t)
            if a.subject == ACME and a.predicate == CTO
        ]

    def staleness_walk(self, aid: str) -> list[str]:
        hit = []
        for c in self.conclusions:
            if aid in c.evidence and c.status == "active":
                c.status = "stale"
                hit.append(c.id)
        return hit


# --------------------------------------------------------------------------
# The inference (E1)
# --------------------------------------------------------------------------

CONSTRAINT_ID = "k1"  # "an Organization has one CTO" — itself citable evidence


def infer_successor_start(log: Log, at: date) -> Optional[Conclusion]:
    """Assume the successor began when the predecessor ended.

    Guardrails, in order:
      - exactly one candidate may have the unknown start (two is guessing)
      - the predecessor's end must be *observed*, never itself inferred, so
        assumptions cannot compound silently
      - a third role-holder in between blocks it
    """
    roles = log.roles_at(at)

    ended = [
        a for a in roles
        if isinstance(a.valid.end, date) and not a.inferred_start
    ]
    open_unknown = [
        a for a in roles if a.valid.start is UNKNOWN and a.valid.end is OPEN
    ]
    if len(ended) != 1 or len(open_unknown) != 1:
        return None

    predecessor, successor = ended[0], open_unknown[0]
    boundary = predecessor.valid.end

    # A third holder covering the boundary means the succession is not direct.
    for other in roles:
        if other.id in (predecessor.id, successor.id):
            continue
        if overlaps(other.valid, Interval(boundary, boundary)) is True:
            return None

    # NOT written onto the assertion. The first version of this file did that,
    # and the conflict then vanished outright rather than becoming explained —
    # the intervals were provably apart, so nothing remained to show. Writing an
    # assumed boundary as though observed destroys the visibility the assumption
    # most needs, and would let the next inference read it as fact. Keeping it in
    # the conclusion makes compounding structurally impossible.
    c = Conclusion(
        id=f"c-inf-{successor.id}",
        statement=(
            f"{successor.object} became {CTO} of {ACME} on {boundary}, "
            f"when {predecessor.object}'s tenure ended"
        ),
        evidence=[predecessor.id, successor.id, CONSTRAINT_ID],
        confidence=0.6,
        derived_by="constraint-inference",
    )
    log.conclusions.append(c)
    return c


def retract(log: Log, c: Conclusion) -> None:
    """Defeat the assumption. Nothing has to be un-written, because nothing was
    written: the conflict simply returns to *possible*, which is the honest
    state it was in before anyone assumed anything."""
    c.status = "retracted"


# --------------------------------------------------------------------------
# Conflict state
# --------------------------------------------------------------------------


def conflict_state(log: Log, at: date) -> str:
    roles = log.roles_at(at)
    worst = "none"
    for i, a in enumerate(roles):
        for b in roles[i + 1:]:
            if a.object == b.object:
                continue
            v = overlaps(a.valid, b.valid)
            if v is True:
                return "conflict"
            if v is None:
                explained = any(
                    c.status == "active"
                    and c.derived_by == "constraint-inference"
                    and {a.id, b.id} <= set(c.evidence)
                    for c in log.conclusions
                )
                worst = "explained" if explained else "possible"
    return worst


def build_log() -> Log:
    log = Log()
    log.add(Assertion("a3", ACME, CTO, "person:diane", Interval(UNKNOWN, OPEN), W1))
    log.add(Assertion("a7", ACME, CTO, "person:bob", Interval(UNKNOWN, OPEN), W3))
    log.conclusions.append(
        Conclusion("c1", "Diane is the decision-maker for the Acme integration",
                   ["a3", "a4", "a5"], 0.72, "llm-judgment")
    )
    # Week 4: a3 closes, a8 restates the fact with a known end.
    a3 = next(a for a in log.assertions if a.id == "a3")
    a3.recorded_until = W4
    log.staleness_walk("a3")
    log.add(Assertion("a8", ACME, CTO, "person:diane", Interval(UNKNOWN, FEB), W4))
    return log


def main() -> None:
    print("Prototype 04 - constraint-driven boundary inference (E1)\n")

    log = build_log()
    print(f"  W3 (both roles open)      : {conflict_state(log, W3)}")
    print(f"  W4 before inference       : {conflict_state(log, W4)}")

    c = infer_successor_start(log, W4)
    print(f"  W4 after inference        : {conflict_state(log, W4)}")
    print(f"    -> {c.statement}")
    print(f"       evidence={c.evidence} confidence={c.confidence} "
          f"derivedBy={c.derived_by}")

    retract(log, c)
    print(f"  W4 after retracting it    : {conflict_state(log, W4)}")

    # No compounding: a second pass must not treat the inferred start as an
    # observed boundary. Re-infer, then try again.
    infer_successor_start(log, W4)
    boundaries_on_assertions = [a.id for a in log.assertions if a.inferred_start]
    print(f"  assumed boundaries written onto assertions: "
          f"{boundaries_on_assertions or 'none - compounding impossible'}")

    print("\n  The conflict is explained, not cleared: the badge carries a")
    print("  citation and a confidence, and defeating the assumption puts the")
    print("  question back rather than losing it.")


if __name__ == "__main__":
    main()
