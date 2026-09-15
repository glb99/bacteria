---
status: proposed
date: YYYY-MM-DD
decision-makers: []
---

# Choose the static Analysis Tools stack for the project

## Context and Problem Statement

The official definition:
Static analysis tools are essential for identifying potential issues in source code without executing the program. These tools help developers ensure code quality, security, and compliance with coding standards.

## Decision Drivers

* Need a way of programatically and deterministically restrinting the codebase (thechnical doubt and slop)
* Need a way of basic security issues detection for a public repository.

## Considered Options

From looking into two referencial codebases (https://github.com/hynek/bgt and https://github.com/fastapi/full-stack-fastapi-template), these are the considered options:
* For Static Application Security Testing:
  * CodeQL: for finding vulnerability issues in codebases (SQL injection, cryptography leakage...), while security-focused, it can also enforce general code quality, maintainability, and code smells (e.g., dead code, unused variables, complex cyclomatic complexity, API misuse)
  * Zizmor: specifically for **GitHub Actions workflows**, finding CI/CD security misconfigurations
* For secrets detection: gitleaks.
* For code quality:
  * ruff: linter (unused imports, bad comparisons, complexity, etc.).
  * mypy: type checker (does this function actually return what it claims, are you passing the right argument types, etc.)
* For dependency scanning: GitHub's Dependabot

## Decision Outcome

Chosen option: adding all the considered, because They do not overlap between them. Some of them are specially useful for the repository's architectural ambitions, like mypy for enforcing the correct use of generic types (https://www.youtube.com/watch?v=PmgHNls70eQ).

### Consequences

* Good, because we obtain an automated platform for ensuring security and quality, so valuable for a public project like this. Also useful if there are several contributors.
* Bad, because some configuration overhead if it was a small (or fast) project (it isn't).

### Confirmation

Tools (added as part of deveopment workflow), detect actual and relevant issues, while no fake positives.

## Pros and Cons of the Options

Not to consider.

## More Information

To be discussed: the way of implementing it as part of local dev workflow, github workflow, both...