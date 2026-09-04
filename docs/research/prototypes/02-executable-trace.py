"""Prototype 02 — the worked example, executed.

Prototype 01 (`01-worked-example.md`) hand-simulated four weeks of input through
the agreed model and reported that it held. That simulation was written by the
same mind that designed the model, which means it could improve the design but
could not falsify it. This file runs the same trace as code so that the
mechanics, rather than the author, decide what happens.

Deliberately tiny and deliberately throwaway, per the repo's CLAUDE.md. Standard
library only. No storage, no LLM, no HTTP, no graph rendering. It exercises
exactly the substrate claims from MENTAL-MODEL.md:

    §3  append-only log, both time axes, assertions addressable by id
    §5  a functional constraint evaluated over valid-time overlap
    §6  evidence links and the staleness walk
    §8  flag-don't-reject: a contradiction is a state, not an error

The question it exists to settle is one the prose glosses over. Week 1 records
`valid[?..]` — an unknown start — and the whole week-3/week-4 mechanism turns on
a valid-time *overlap test* between two role assertions. Nowhere does the model
say what an unknown bound means to that predicate, and a human reading `[?..]`
fills in the intent without noticing. Three readings are implemented below and
the trace is run under each.

Run: `python 02-executable-trace.py`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

# --------------------------------------------------------------------------
# Time
# --------------------------------------------------------------------------

W1 = date(2026, 5, 4)
W2 = date(2026, 5, 11)
W3 = date(2026, 5, 18)
W4 = date(2026, 5, 25)
FEB = date(2026, 2, 15)  # when Diane actually left — learned in week 4


class Bounds(Enum):
    """How an unknown temporal bound is read by the overlap test.

    The model never chose one. Each is defensible and they disagree.
    """

    OPEN = "open"  # unknown start = -inf, unknown end = +inf
    STRICT = "strict"  # an unknown bound cannot be proven to overlap
    THREE = "three-valued"  # unknown bounds yield UNKNOWN, not a verdict


@dataclass(frozen=True)
class Interval:
    """Valid time. `None` means the bound is unknown *or* open — see finding 3."""

    start: Optional[date] = None
    end: Optional[date] = None

    def __str__(self) -> str:
        s = self.start.isoformat() if self.start else "?"
        e = self.end.isoformat() if self.end else "?"
        return f"[{s}..{e}]"


def overlaps(a: Interval, b: Interval, policy: Bounds) -> Optional[bool]:
    """Do two valid intervals overlap? `None` means 'cannot be determined'."""
    definitely_apart = (
        a.end is not None and b.start is not None and a.end <= b.start
    ) or (b.end is not None and a.start is not None and b.end <= a.start)

    if policy is Bounds.OPEN:
        lo = max(a.start or date.min, b.start or date.min)
        hi = min(a.end or date.max, b.end or date.max)
        return lo < hi

    if policy is Bounds.STRICT:
        if None in (a.start, a.end, b.start, b.end):
            return False
        return not definitely_apart

    # THREE: answer only when the unknowns cannot change it. Deliberately
    # conservative — 'definitely true' requires every bound known.
    if definitely_apart:
        return False
    if None in (a.start, a.end, b.start, b.end):
        return None
    return True


# --------------------------------------------------------------------------
# The log (§3)
# --------------------------------------------------------------------------


@dataclass
class Assertion:
    """One claim, addressable by id, with both time axes and its provenance."""

    id: str
    subject: str
    predicate: str
    object: str
    valid: Interval
    recorded_at: date
    recorded_until: Optional[date] = None  # None = still believed
    source: str = "conversation"
    actor: str = "agent"
    inferred: bool = False  # derived boundary, not observed

    def believed_at(self, t: date) -> bool:
        return self.recorded_at <= t and (
            self.recorded_until is None or self.recorded_until > t
        )


@dataclass
class Conclusion:
    """A belief with mandatory evidence links (§6)."""

    id: str
    statement: str
    evidence: list[str]
    confidence: float
    status: str = "active"  # active | stale
    recorded_at: date = W2


@dataclass
class Log:
    """Append-only. Nothing is ever deleted; recorded intervals are closed."""

    assertions: list[Assertion] = field(default_factory=list)
    conclusions: list[Conclusion] = field(default_factory=list)

    def append(self, a: Assertion) -> Assertion:
        self.assertions.append(a)
        return a

    def by_id(self, aid: str) -> Assertion:
        return next(a for a in self.assertions if a.id == aid)

    def state_at(self, t: date) -> list[Assertion]:
        """The projection: what was believed at recorded-time `t`."""
        return [a for a in self.assertions if a.believed_at(t)]

    def supersede(self, aid: str, new_id: str, new_valid: Interval, at: date,
                  actor: str = "user") -> Assertion:
        """Revise a fact without overwriting it: close the old, append the new."""
        old = self.by_id(aid)
        old.recorded_until = at
        self.staleness_walk(aid)
        return self.append(
            Assertion(
                id=new_id,
                subject=old.subject,
                predicate=old.predicate,
                object=old.object,
                valid=new_valid,
                recorded_at=at,
                source=old.source,
                actor=actor,
            )
        )

    def staleness_walk(self, aid: str) -> list[str]:
        """§6: walk evidence links from a revised assertion to its dependents."""
        hit = []
        for c in self.conclusions:
            if aid in c.evidence and c.status == "active":
                c.status = "stale"
                hit.append(c.id)
        return hit


# --------------------------------------------------------------------------
# The constraint (§5)
# --------------------------------------------------------------------------

Conflict = tuple[str, str, Optional[bool]]


def functional_conflicts(
    log: Log, at: date, subject: str, predicate: str, policy: Bounds,
    infer_boundaries: bool = False,
) -> list[Conflict]:
    """'An Organization has one CTO' — at most one object, at any one moment.

    Returns (id, id, verdict) where verdict True is a conflict and None is a
    conflict that cannot be decided because a bound is unknown.
    """
    live = [
        a
        for a in log.state_at(at)
        if a.subject == subject and a.predicate == predicate
    ]
    if infer_boundaries:
        live = _infer_successor_starts(live)

    out: list[Conflict] = []
    for i, a in enumerate(live):
        for b in live[i + 1:]:
            if a.object == b.object:
                continue
            verdict = overlaps(a.valid, b.valid, policy)
            if verdict is not False:
                out.append((a.id, b.id, verdict))
    return out


def _infer_successor_starts(live: list[Assertion]) -> list[Assertion]:
    """If one role ends at E and another has an unknown start, assume it began at E.

    This is what a human does automatically — Bob became CTO when Diane left.
    Note what it is: an *assumption*, not an observation. There could have been
    a gap with no CTO at all. See finding 2.
    """
    ends = sorted({a.valid.end for a in live if a.valid.end is not None})
    if not ends:
        return live
    latest_end = ends[-1]
    out = []
    for a in live:
        if a.valid.start is None and a.valid.end is None:
            out.append(
                Assertion(
                    **{
                        **a.__dict__,
                        "valid": Interval(start=latest_end, end=None),
                        "inferred": True,
                    }
                )
            )
        else:
            out.append(a)
    return out


# --------------------------------------------------------------------------
# The trace
# --------------------------------------------------------------------------

ACME = "org:acme"
CTO = "cto"


def build_log() -> Log:
    log = Log()

    # Week 1 — "Had coffee with Diane from Acme, she's their CTO."
    log.append(Assertion("a1", "person:diane", "isa", "Person", Interval(), W1))
    log.append(Assertion("a2", ACME, "isa", "Organization", Interval(), W1))
    log.append(Assertion("a3", ACME, CTO, "person:diane", Interval(), W1))
    log.append(
        Assertion("a4", "event:coffee", "topic", "integration", Interval(W1, W1), W1)
    )

    # Week 2 — the email, the merge, the conclusion.
    log.append(
        Assertion("a5", "person:diana", "email", "diana@acme.com", Interval(), W2,
                  source="email")
    )
    log.append(
        Assertion("a6", "person:diane", "sameAs", "person:diana", Interval(), W2,
                  actor="user")
    )
    log.conclusions.append(
        Conclusion(
            "c1",
            "Diane is the decision-maker for the Acme integration",
            evidence=["a3", "a4", "a5"],
            confidence=0.72,
        )
    )

    # Week 3 — the newsletter. Lands; does not reject anything.
    log.append(
        Assertion("a7", ACME, CTO, "person:bob", Interval(), W3, source="newsletter")
    )

    # Week 4 — "Diane left Acme back in February."
    # Append-only: a3 is not edited. Its recorded interval closes and a8 states
    # the same fact with a known end.
    log.supersede("a3", "a8", Interval(start=None, end=FEB), at=W4)

    return log


# --------------------------------------------------------------------------
# The four claims prototype 01 made
# --------------------------------------------------------------------------


def run(policy: Bounds, infer: bool) -> dict[str, object]:
    log = build_log()

    at_w3 = functional_conflicts(log, W3, ACME, CTO, policy, infer)
    at_w4 = functional_conflicts(log, W4, ACME, CTO, policy, infer)
    c1 = log.conclusions[0]
    believed_w2 = {a.id for a in log.state_at(W2)}

    return {
        "conflict fires at W3": bool(at_w3) and at_w3[0][2] is True,
        "undecided at W3": bool(at_w3) and at_w3[0][2] is None,
        "clears at W4, no user action": not at_w4,
        "c1 goes stale": c1.status == "stale",
        "state_at(W2) is the W2 belief": "a3" in believed_w2 and "a8" not in believed_w2,
    }


CLAIMS = [
    "conflict fires at W3",
    "clears at W4, no user action",
    "c1 goes stale",
    "state_at(W2) is the W2 belief",
]


def main() -> None:
    print("Prototype 02 - the worked example, executed\n")

    width = max(len(c) for c in CLAIMS) + 2
    header = "policy".ljust(16) + "infer".ljust(8) + "".join(
        c.ljust(width) for c in CLAIMS
    )
    print(header)
    print("-" * len(header))

    for policy in Bounds:
        for infer in (False, True):
            r = run(policy, infer)
            cells = []
            for c in CLAIMS:
                if c == "conflict fires at W3" and r["undecided at W3"]:
                    cells.append("undecided".ljust(width))
                else:
                    cells.append(("PASS" if r[c] else "FAIL").ljust(width))
            print(policy.value.ljust(16) + str(infer).ljust(8) + "".join(cells))

    print("\n--- the log after week 4 ---")
    log = build_log()
    for a in log.assertions:
        until = a.recorded_until.isoformat() if a.recorded_until else "still believed"
        print(
            f"  {a.id}  {a.subject:14} {a.predicate:8} {a.object:18} "
            f"valid{str(a.valid):26} recorded[{a.recorded_at} .. {until}]"
        )
    for c in log.conclusions:
        print(f"  {c.id}  {c.statement!r} evidence={c.evidence} status={c.status}")


if __name__ == "__main__":
    main()
