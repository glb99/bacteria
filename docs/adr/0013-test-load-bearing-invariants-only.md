# 0013 — Test load-bearing invariants only

## Status

Accepted — 2026-08-06

## Context

Two failure modes in testing a system like this, and they pull in opposite
directions.

Test too little and the boundaries that justify the whole layered structure are
unprotected — the model layer gains the ability to execute something, a retry
starts repeating a side effect, and nothing notices until it matters.

Test everything and the suite fills with assertions about decisions that have no
runtime behavior at all. "We chose a narrow protocol over a provider abstraction
layer" is a real decision worth recording, and there is nothing to assert about
it. Tests written to cover such decisions end up asserting implementation detail,
which makes refactoring expensive and protects nothing.

A coverage percentage gate makes this worse rather than better: it rewards
writing exactly the tests this project has decided not to write.

## Decision

Split every design decision into one of two kinds and route it accordingly.

**Load-bearing invariants** — claims about behavior whose silent violation
causes a real bug. These get an automated test that fails when the invariant
breaks. They are [architectural fitness
functions](https://www.thoughtworks.com/insights/books/building-evolutionary-architectures):
executable, repeatable checks that a structural property still holds. Examples:
a handler never reaches the model; a rejection means nothing ran; only
`ServingError` retries; a failed run still commits evidence.

**Rationale decisions** — judgment calls about why something is built a
particular way, with no runtime behavior to assert. These get an ADR and no test.

Keep the count per module small and deliberate. A handful of genuinely
load-bearing boundaries, not one test per decision.

Prefer a real end-to-end run over mocks alone when verifying a module, and try
specifically to reproduce known failure modes rather than only the happy path.

No coverage gate.

## Consequences

Every test earns its place, and a failing test means something is actually
wrong — which is what makes the suite worth reading when it goes red.

Test docstrings state the invariant and the consequence of breaking it, so they
document the architecture as well as verifying it.

Coverage is uneven by design. Some modules are thoroughly tested and others
barely, according to how much would break rather than how many lines they have.
That looks like negligence on a coverage report and is the intended outcome.

Bugs in non-invariant code will not be caught by this suite. Accepted: the
alternative is a suite large enough that nobody reads a failure carefully.

The judgment call — is this invariant load-bearing? — is made by a person, and
it will sometimes be made wrong. The live discovery of Gemini's
`thought_signature` requirement is the case in point: every mocked test passed
while real multi-turn tool calls failed, which is the argument for the
end-to-end clause above.
