"""`just check-all` and the workflows must agree about what the gate is.

Two hand-maintained lists describe one gate. `check-all` is what a person runs
before pushing; `.github/workflows/` is what actually blocks a merge. Nothing
forces them to match, and the divergence is silent in both directions: a check
that runs only in CI is one people discover by being rejected, and a check that
runs only locally stops anyone from noticing when it breaks.

**This already happened here.** Coverage measures the application and
deliberately not the agent (ADR 0013), so `cov` does not run
`backend/agent/tests`. That part is correct. What followed was not: "excluded
from the coverage report" quietly became "not run by the gate", and the agent's
architectural fitness functions -- the tests most worth running before shipping
-- were the ones `check-all` skipped. The Justfile still carries the note.

The point is not that the two lists must be identical. They are not, for good
reasons, and every difference is spelled out in :data:`RUN_ONLY_IN_CI` and
:data:`RUN_ONLY_LOCALLY` with the argument for it. The point is that adding a
difference should cost writing the argument down.
"""

import pathlib
import re

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOWS = REPOSITORY_ROOT / ".github" / "workflows"
JUSTFILE = REPOSITORY_ROOT / "justfile"

RUN_ONLY_IN_CI = {
    "db-up": "A precondition, not a check. `check-all` demands a database rather than "
    "starting one -- starting Docker on someone's behalf is a surprise -- and the suite "
    "now fails rather than skipping when it is missing.",
    "migrate": "A precondition here and a deployment step in deploy.yml. That migrations "
    "and models agree is asserted by test_migrations.py, which `cov` does run.",
    "smoke": "Spawns real processes and writes into whatever database it is pointed at. "
    "Wrong shape for a fast pre-push gate, which is also why it is a workflow of its own "
    "rather than a job in test.yml.",
    "stack-smoke": "Builds a Docker image from scratch and needs a daemon. Minutes, not "
    "seconds. The exit route off FastAPI Cloud has to be gated somewhere, and that "
    "somewhere is not a recipe people run between edits.",
    "stack-down": "Teardown, not a check. It runs in an `always()` step so a failed "
    "run still releases the runner, and it removes the Postgres volume -- right on a "
    "disposable runner and destructive anywhere else, which is why `stack-stop` exists "
    "for local use.",
}
"""Recipes a workflow runs that `just check-all` deliberately does not."""

RUN_ONLY_LOCALLY = {
    "audit-ci": "zizmor runs in CI as `zizmorcore/zizmor-action` rather than through this "
    "recipe, because the action turns findings into inline annotations on the pull "
    "request's Files tab. Same tool and same configuration; only the reporting differs, "
    "so the gate is covered and the name is not."
}
"""Recipes `just check-all` runs that no workflow invokes by that name."""

INVOCATION = re.compile(r"\buv run just ([a-z0-9][a-z0-9-]*)")


def _without_comments(text):
    """Drop whole-line YAML comments before looking for invocations.

    These workflows explain at length what other recipes do and why, and naming
    a recipe is not running it. Without this, the prose that makes them readable
    would decide what the gate is.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _recipes_run_by_workflows():
    invocations = {}
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        text = _without_comments(workflow.read_text(encoding="utf-8"))
        for recipe in INVOCATION.findall(text):
            invocations.setdefault(recipe, set()).add(workflow.name)
    return invocations


def _check_all_dependencies():
    for line in JUSTFILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("check-all:"):
            return line.split(":", 1)[1].split()
    raise AssertionError(f"no `check-all:` recipe in {JUSTFILE}")


def test_the_parsers_find_something():
    """Guard the guard: a pattern that matches nothing agrees with everything.

    This is the failure mode of every check built on parsing files it does not
    own. Rename `check-all`, restructure a workflow step, and the assertions
    below start comparing two empty sets and reporting harmony. It is the same
    shape as the `sed` in deploy.yml that had to be followed by a
    `git check-ignore`, and it is here for the same reason.
    """
    assert JUSTFILE.is_file(), f"no justfile at {JUSTFILE}"
    assert WORKFLOWS.is_dir(), f"no workflows at {WORKFLOWS}"

    dependencies = _check_all_dependencies()
    assert len(dependencies) >= 5, f"`check-all` has suspiciously few steps: {dependencies}"

    invocations = _recipes_run_by_workflows()
    assert len(invocations) >= 5, f"barely any `uv run just` in the workflows: {invocations}"


def test_every_recipe_ci_runs_is_in_check_all_or_explained():
    """A merge-blocking check must be one a person can run before pushing.

    test.yml states the rule in its own header -- "a check that only exists in
    CI is a check people discover by having it reject them" -- and this is what
    holds it to it. The allowlist is not a way around that: an entry is a
    written argument that the recipe belongs only in CI, and re-reading those
    arguments is how the next person decides whether they still hold.
    """
    in_check_all = set(_check_all_dependencies())

    unexplained = {
        recipe: sorted(workflows)
        for recipe, workflows in _recipes_run_by_workflows().items()
        if recipe not in in_check_all and recipe not in RUN_ONLY_IN_CI
    }

    assert not unexplained, (
        "these recipes run in CI but not in `just check-all`:\n"
        + "\n".join(f"  - {recipe}, in {', '.join(files)}" for recipe, files in unexplained.items())
        + "\n\nEither add them to `check-all` in the justfile, or add them to RUN_ONLY_IN_CI "
        "in this file with the reason they belong only in CI."
    )


def test_every_recipe_check_all_runs_is_in_ci_or_explained():
    """The other direction, which decays instead of failing.

    A recipe only `check-all` runs is not a broken gate -- it is a gate nothing
    enforces. It blocks no merge and passes for whoever ran it last, so it can
    rot without a single run going red. Cheaper to notice here than to find out
    that a check everyone believed in has been failing on `main` for a month.
    """
    run_by_ci = set(_recipes_run_by_workflows())

    unexplained = [
        recipe
        for recipe in _check_all_dependencies()
        if recipe not in run_by_ci and recipe not in RUN_ONLY_LOCALLY
    ]

    assert not unexplained, (
        f"`just check-all` runs {unexplained}, which no workflow runs, so nothing enforces "
        "them. Either add them to a workflow, or add them to RUN_ONLY_LOCALLY in this file "
        "with the reason CI covers them another way."
    )


@pytest.mark.parametrize("allowlist", [RUN_ONLY_IN_CI, RUN_ONLY_LOCALLY])
def test_the_allowlists_hold_no_entry_that_stopped_being_true(allowlist):
    """An exemption for a recipe that no longer exists is worse than none.

    It reads as a considered decision about the gate as it stands and is a
    leftover from an older one. It also pre-approves the name, so a future
    recipe that reuses it inherits an argument nobody made about it.
    """
    known = set(_check_all_dependencies()) | set(_recipes_run_by_workflows())
    stale = sorted(set(allowlist) - known)

    assert not stale, (
        f"these are exempted but named by neither `check-all` nor any workflow: {stale}. "
        "They were renamed or removed; delete the entries."
    )
