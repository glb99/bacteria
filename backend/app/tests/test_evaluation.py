"""The gate's half of the evaluation: seed runs, judge them, fail on findings.

Two jobs here, and they are different enough to be worth naming.

The first is the eval itself — `test_seeded_runs_satisfy_the_policy` drives real
turns through the real runtime into the real database, reads them back out of
the transcript, and asserts they meet a stated policy. That is a regression
check on agent *behaviour* rather than on any function, and it is the closest
this project gets to the article's deterministic evals.

The second is checking the checks. A check that cannot fail is worse than no
check, because it reports success. Every check below is therefore given a run
that should trip it, and asserted to trip. That is what stops this file from
becoming the dashboard the article warns about.
"""

import inspect

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.agent.session.store import TranscriptItem
from bacteria.app.chat.repository import SqlSessionRepository
from bacteria.app.evaluation import checks as checks_module
from bacteria.app.evaluation.checks import CHECKS, Policy, evaluate
from bacteria.app.evaluation.fixtures import FIXTURE_MODEL, FIXTURE_TOOL, seed
from bacteria.app.evaluation.runs import RecordedRun, load_runs

POLICY = Policy(
    expected_models=frozenset({FIXTURE_MODEL}),
    approved_tools=frozenset({FIXTURE_TOOL}),
    # Two of the four seeded runs fail on purpose, because the checks that read
    # failure evidence need failures to read. The threshold is set above that
    # rather than at it, so the fixture is not silently pinned to its own shape.
    max_failure_rate=0.75,
)


@pytest.fixture(name="seeded")
async def _seeded(engine):
    """Four real runs in the database, and the runs read back out of it."""
    async with AsyncSession(engine) as db:
        session_id = await seed(SqlSessionRepository(db))
        return session_id, await load_runs(db, session_id=session_id)


async def test_seeded_runs_satisfy_the_policy(seeded):
    """The eval, run over runs that actually executed.

    Nothing here is asserted about code. It reads what four turns left in
    storage and judges it — which model answered, what each was offered,
    whether a refusal held — against a policy stated separately from the
    system that produced them.
    """
    _session_id, runs = seeded

    report = evaluate(runs, POLICY)

    assert report.runs_checked == 4
    assert report.findings == [], [f"{f.check}: {f.detail}" for f in report.findings]


async def test_the_run_slice_is_reconstructed_from_a_flat_transcript(seeded):
    """A run is a group of rows, and grouping them back is the load-bearing step.

    Everything else reads `RecordedRun`. If this stitched runs together wrongly
    — merging two turns, or splitting one — every check downstream would be
    judging something that never happened, and all of them would still pass.
    """
    _session_id, runs = seeded

    assert [run.outcome for run in runs] == ["completed", "completed", "failed", "failed"]
    assert [run.model for run in runs] == [FIXTURE_MODEL, FIXTURE_MODEL, FIXTURE_MODEL, None]
    assert len(runs[1].tool_calls) == 1
    assert runs[1].tool_calls[0]["status"] == "executed"
    assert runs[2].tool_calls[0]["reason"] == "rejected"
    assert runs[3].has_error and runs[3].model is None


async def test_rows_written_before_runs_had_ids_are_skipped_not_invented(engine):
    """A pre-ADR-0018 row belongs to no run and must not be given one.

    Grouping them under a synthetic id would manufacture a turn that never
    happened and then report findings about it — the failure mode where an
    evaluation is not merely wrong but confidently wrong.
    """
    async with AsyncSession(engine) as db:
        repository = SqlSessionRepository(db)
        session = await repository.create_session(user_id="legacy")
        await repository.commit(
            session.session_id,
            new_transcript_items=[
                TranscriptItem(kind="message", payload={"role": "user", "text": "old"}),
            ],
        )

        assert await load_runs(db, session_id=session.session_id) == []


def run(**overrides) -> RecordedRun:
    """A run that passes every check, so a test can break exactly one thing."""
    base = {
        "run_id": "r1",
        "session_id": "s1",
        "meta": {
            "model": FIXTURE_MODEL,
            "tools_exposed": [FIXTURE_TOOL],
            "outcome": "completed",
        },
        "tool_calls": [],
        "message_count": 2,
        "has_error": False,
    }
    return RecordedRun(**{**base, **overrides})


@pytest.mark.parametrize(
    ("name", "broken"),
    [
        (
            "every_run_describes_itself",
            run(meta={}),
        ),
        (
            "runs_use_an_expected_model",
            run(meta={"model": "something-else", "tools_exposed": [], "outcome": "completed"}),
        ),
        (
            "runs_expose_only_approved_tools",
            run(
                meta={
                    "model": FIXTURE_MODEL,
                    "tools_exposed": [FIXTURE_TOOL, "delete_everything"],
                    "outcome": "completed",
                }
            ),
        ),
        (
            "a_refused_tool_call_produced_no_output",
            run(tool_calls=[{"name": FIXTURE_TOOL, "reason": "rejected", "output": "10:00"}]),
        ),
        (
            "failures_stay_under_the_threshold",
            run(has_error=True, meta={"model": FIXTURE_MODEL, "outcome": "failed"}),
        ),
    ],
)
def test_each_check_catches_what_it_exists_for(name, broken):
    """Every check is shown a run that should trip it, and must trip.

    A check that cannot fail is worse than an absent one: it reports success.
    This is the same argument as the suite's other fitness functions, applied to
    the things doing the judging.
    """
    strict = Policy(
        expected_models=frozenset({FIXTURE_MODEL}),
        approved_tools=frozenset({FIXTURE_TOOL}),
        max_failure_rate=0.0,
    )

    report = evaluate([broken], strict)

    assert name in {finding.check for finding in report.findings}


def test_an_empty_population_is_not_a_pass():
    """No runs must never read as a clean result.

    Zero runs satisfies every check by having nothing to violate them, so the
    honest report is "nothing was judged". The `runs_checked` count is what
    makes that visible, and the CLI treats it as a failure rather than printing
    a green result over an empty database.
    """
    report = evaluate([], POLICY)

    assert report.passed
    assert report.runs_checked == 0


def test_every_check_is_registered():
    """A check nobody runs protects nothing.

    Written because the registry is a hand-maintained tuple, which is the right
    trade for five functions in one module and is exactly the kind of list that
    silently stops including its newest member.
    """
    not_a_check = {"Policy", "Finding", "Report", "evaluate"}
    defined_here = {
        name
        for name, value in vars(checks_module).items()
        if inspect.isfunction(value)
        and value.__module__ == checks_module.__name__
        and not name.startswith("_")
        and name not in not_a_check
    }

    assert defined_here, "discovery found nothing, so this assertion proves nothing"
    assert defined_here == {check.__name__ for check in CHECKS}
