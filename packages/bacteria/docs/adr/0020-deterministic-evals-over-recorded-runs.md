# 0020 — Judge recorded runs with deterministic checks, seeded rather than captured

## Status

Accepted — 2026-08-11

## Context

[ADR 0018](0018-transcript-items-carry-their-run-id.md) made runs identifiable
and [ADR 0019](0019-a-run-records-how-it-was-configured.md) made them
self-describing. Both produce evidence. Neither judges it, and Part 8 is
insistent that these are different jobs: a trace explains what happened and
decides nothing.

The article splits judgment three ways — deterministic checks, rubric scoring,
and human review — and is blunt about the first: write an assertion rather than
asking a model to prove something the system can already state. Every question
worth asking of this agent is in that first category. Which model answered.
What it was offered. Whether a refusal held before the side effect. None of
those need an opinion.

The project already has assertions, and they are not this. `test_a_run_records_how_it_was_configured`
runs a fake client against an in-memory store before release. A deterministic
eval reads runs that already ran. Same mechanism, different subject — which is
the distinction the Part 8 discussion drew and the reason having one does not
give you the other.

## Decision

Checks are a library over plain objects, with two drivers.

`fastpaip.evaluation.runs` rebuilds a run by grouping transcript rows on
`run_id`. `fastpaip.evaluation.checks` judges a sequence of those against a
`Policy` and returns findings. Neither knows who called it.

That separation is the decision. The gate seeds fixtures and asserts; `fastpaip-admin
eval` reads whatever a deployment did. One set of checks, so a rule cannot pass
in CI and mean something else in production.

**Seeded fixtures, not captured traffic.** Real transcripts hold user text and
tool arguments verbatim, there is no retention rule and no delete route.
Building a gate that depends on keeping them would settle the retention question
by accident, in the direction of keeping everything, without anyone deciding it.
Fixtures also make the gate deterministic, which captured traffic is not.

**Fixtures drive the real runtime.** Every seeded run goes through `Runtime`
against the real repository with only the model faked. Inserting transcript rows
directly would write the answer the checks read back, and would keep passing
after the runtime stopped producing that shape.

**A check takes the whole population, not one run.** A failure *rate* is only
askable of a set, and one signature for all five is worth more than a narrower
one for the four.

**Findings carry `run_id`.** A finding you cannot trace to its evidence is a
number. This is what ADR 0018 was for.

**An empty population is not a pass.** Zero runs satisfies every check by having
nothing to violate, so the CLI reports "nothing was judged" and exits non-zero
rather than printing a clean result over an empty database.

**The gate fails on findings.** A report nobody must act on is the dashboard the
article warns about. This is the smallest thing that is not one.

## Consequences

Five checks now run on every `just check-all`: every run describes itself, runs
used an expected model, no run was offered an unapproved tool, a refused tool
call produced no output, and failures stayed under a threshold. Each is given a
run that should trip it and asserted to trip — a check that cannot fail is worse
than an absent one, because it reports success.

Pointed at the development database, the first real run found four runs with no
`run_meta`. Correct: they were written during ADR 0018's verification, before
ADR 0019 existed. Any deployment adopting this will see the same thing for its
own history, and the finding is real rather than noise — those runs genuinely
cannot be reconstructed. There is no backfill and there should not be.

**What this is not, stated plainly because the name invites overclaiming.** It
judges runs this project wrote to exercise its own checks. That is regression
value on agent behaviour, and it is not the article's evaluation of production
behaviour — no user ever saw these turns. The feedback loop is also still
missing: nothing turns a finding into a dataset item, a prompt change, or a
policy change. The gate blocking is one end of that loop with nothing attached
to the other.

Not built: rubric checks and model-graded judgment, both of which need
calibration and a human; per-check severity, so a policy cannot warn on one
finding and block on another; and any check over identity or approval *grants*,
because a gate that allows everything records nothing to check.
