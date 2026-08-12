"""Deterministic judgments about runs that already happened.

The distinction this module exists to hold, from Part 8 of the series: a trace
explains what happened and decides nothing. These decide. They are the
*deterministic* kind of evaluation — assertions with a definite answer — and
deliberately not the other two kinds. There is no rubric here and no model
judging another model's output, because everything below is something the
system can already prove about itself, and asking a model to opine on a fact
you can assert is how a check becomes an opinion.

What separates these from the test suite is subject, not mechanism. A test
checks code against inputs it constructed, before release. These read evidence
of runs that already ran, and are equally pointable at a database nobody was
watching. That is why they are a library rather than test functions: the gate
drives them over seeded fixtures, and ``bacteria-admin eval`` drives the same
code over whatever a deployment actually did.

Every check is a function over the whole set rather than over one run. Some
questions are only askable of a population — a failure *rate* is the obvious
one — and one shape for all of them is worth more than a narrower signature for
the majority.

Not built:
    Rubric checks and model-graded judgment. Both are real parts of the
    article's taxonomy and neither belongs here: they need calibration and a
    human in the loop, where these need a database.

    Per-check severity. Every finding weighs the same, so a policy cannot say
    "warn on this, block on that". Adding it before anything wants it would be
    inventing a policy language for one caller.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from bacteria.app.evaluation.runs import RecordedRun


@dataclass(frozen=True)
class Policy:
    """What the runs are being judged against.

    Passed in rather than read from settings, because the answer differs by who
    is asking: the gate judges seeded fixtures against what those fixtures were
    built to do, and an operator judges production against what production is
    supposed to be configured with. A single global would force those to agree.

    Attributes:
        expected_models: Models a run is permitted to have been answered by.
            A set, not one value, so a deployment mid-migration between two
            pinned models is expressible without turning the check off.
        approved_tools: Tools a run is permitted to have been offered. The
            check is on what was *exposed*, not on what was called — a tool the
            model was shown is a tool it could have used, and the moment to
            notice an unintended one is before it is picked.
        max_failure_rate: Proportion of runs allowed to have failed, between 0
            and 1. A rate rather than a count, because a count that is fine for
            a day is an incident for an hour.
    """

    expected_models: frozenset[str] = frozenset()
    approved_tools: frozenset[str] = frozenset()
    max_failure_rate: float = 1.0


@dataclass(frozen=True)
class Finding:
    """One thing a check objected to.

    Carries ``run_id`` so that a finding is actionable: the id selects the
    evidence it came from, which is the entire reason ADR 0018 exists. Aggregate
    findings have no single run and leave it ``None``.
    """

    check: str
    detail: str
    run_id: str | None = None


Check = Callable[[Sequence[RecordedRun], Policy], Iterable[Finding]]


def every_run_describes_itself(runs: Sequence[RecordedRun], policy: Policy) -> Iterable[Finding]:
    """A run that wrote evidence must also say how it was configured.

    First, because it is the check that protects the others. A run with no
    ``run_meta`` passes every model and tool assertion below by having nothing
    to disagree with, so a regression that stopped writing the record would look
    like a clean bill of health rather than a gap.
    """
    for run in runs:
        if not run.meta:
            yield Finding(
                check="every_run_describes_itself",
                run_id=run.run_id,
                detail=f"run wrote {run.message_count} message(s) and no run_meta",
            )


def runs_use_an_expected_model(runs: Sequence[RecordedRun], policy: Policy) -> Iterable[Finding]:
    """Nothing answered on a model this deployment did not intend to use.

    Checked only for runs that completed. A run that failed before the model
    replied has no model to name, and reporting that as a wrong model would
    make every outage look like a misconfiguration.
    """
    if not policy.expected_models:
        return
    for run in runs:
        if not run.completed:
            continue
        if run.model not in policy.expected_models:
            yield Finding(
                check="runs_use_an_expected_model",
                run_id=run.run_id,
                detail=f"answered by {run.model!r}, expected one of {sorted(policy.expected_models)}",
            )


def runs_expose_only_approved_tools(
    runs: Sequence[RecordedRun], policy: Policy
) -> Iterable[Finding]:
    """No run offered the model a capability outside the approved set."""
    for run in runs:
        unapproved = sorted(set(run.tools_exposed) - policy.approved_tools)
        if unapproved:
            yield Finding(
                check="runs_expose_only_approved_tools",
                run_id=run.run_id,
                detail=f"exposed unapproved tool(s): {unapproved}",
            )


def a_refused_tool_call_produced_no_output(
    runs: Sequence[RecordedRun], policy: Policy
) -> Iterable[Finding]:
    """The approval boundary held, according to the record it left.

    This is the one check here that judges the *path* rather than the
    configuration, and it is the article's example almost verbatim: did the
    system get approval before the side effect. A refused call carrying output
    means the handler ran and the refusal was recorded afterwards, which is a
    gate in name only.

    It reads `reason` rather than the error message, which is why bacteria's
    ADR 0019 made that field structural — a check that string-matched an
    exception would silently stop working when someone reworded it.
    """
    for run in runs:
        for call in run.tool_calls:
            if call.get("reason") == "rejected" and "output" in call:
                yield Finding(
                    check="a_refused_tool_call_produced_no_output",
                    run_id=run.run_id,
                    detail=f"{call.get('name')!r} was refused and still recorded output",
                )


def failures_stay_under_the_threshold(
    runs: Sequence[RecordedRun], policy: Policy
) -> Iterable[Finding]:
    """Runs fail sometimes; they should not fail often.

    The only aggregate check, and the only one whose verdict depends on how many
    runs it was given — a single failed run is 100% of a population of one. That
    is a real limitation rather than a bug, and it is why this reports the
    counts alongside the rate instead of only the verdict.
    """
    if not runs:
        return
    failed = [run for run in runs if run.has_error or run.outcome == "failed"]
    rate = len(failed) / len(runs)
    if rate > policy.max_failure_rate:
        yield Finding(
            check="failures_stay_under_the_threshold",
            detail=(
                f"{len(failed)}/{len(runs)} runs failed ({rate:.0%}), "
                f"above the {policy.max_failure_rate:.0%} threshold"
            ),
        )


CHECKS: tuple[Check, ...] = (
    every_run_describes_itself,
    runs_use_an_expected_model,
    runs_expose_only_approved_tools,
    a_refused_tool_call_produced_no_output,
    failures_stay_under_the_threshold,
)
"""Every check, in the order a report should read them.

A tuple rather than a registry with decorators: five functions in one module do
not need discovery, and an explicit list is the one place to look to answer
"what is actually being judged".
"""


@dataclass(frozen=True)
class Report:
    """The outcome of judging a set of runs.

    Attributes:
        runs_checked: Reported even when nothing failed, because "no findings"
            over zero runs and "no findings" over four hundred are different
            statements and a report that prints the same thing for both is
            misleading in the more dangerous direction.
    """

    runs_checked: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.findings


def evaluate(
    runs: Sequence[RecordedRun], policy: Policy, checks: Sequence[Check] = CHECKS
) -> Report:
    """Apply every check and collect what they object to.

    Runs all of them rather than stopping at the first failure. A report that
    stopped early would make fixing one problem reveal the next, which turns a
    single review into a queue.
    """
    findings = [finding for check in checks for finding in check(runs, policy)]
    return Report(runs_checked=len(runs), findings=findings)
