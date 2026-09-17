---
status: proposed
date: YYYY-MM-DD
decision-makers: []
---

# Enforce pre-commit checks in GitHub Actions

## Context and Problem Statement

We have a pre-commit.conf runned by prek, it will run part of our SATs, we must define where it runs.

## Decision Drivers

* Making SATs actually valuable, and have a standarized and well-knowed way of how are they executed.

## Considered Options

* Separating SATs execution in two: the ones executed in pre-commit and the ones executed as workflow actions.
* Running the pre-commit as part of an actions workflow.

## Decision Outcome

Chosen option: "Running the pre-commit as part of an actions workflow", because it makes SATs valuable by not allowing to bypass them, so there is no way a contributor forgets to execute the pre-commit via prek, in that case doesn't matter becase the workflow action will give a second confirmation.

### Execution model

Code quality SATs (Ruff, Ruff format, mypy, ty, Biome, typos and zizmor) are executed both by prek locally as pre-commit hooks and from the precommit **PR** workflow.

Zizmor is the only tool that overlaps a pre-commit hook with an actions workflow, this is intended as it si a light-weight process and it is distributed as a python package (can be executed from uv), unlike other SASTs like codeql. This allows to detect problems locally before pushing the branch.

CodeQL, the tests, dependabot and gitleaks have its own actions workflows.

### Consequences

* Good, because every contribution receives the same validation.
* Good, because there is still an optional way of executing it as part of the local dev workflow.
* Bad, because CI growns in complexity and execution time.
* Bad, some auto-fix may modify a contributor’s PR branch.

### Confirmation

Try the configuration, analyse if:
* It detects valuable items.
* If not, it doesn't generate some "false positives" that overheads the development.

## Pros and Cons of the Options

Not to consider.

## More Information

* Implements the CI/local execution approach for
  [ADR 0003 — Choose the static analysis tools stack](0003-choose-static-analysis-tools-
  stack.md).