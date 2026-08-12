<!--
Keep one concern per pull request. See CONTRIBUTING.md for the conventions this
repository uses for commits, branches, and naming.
-->

## What changes, and why

<!-- State the change in behaviour, not the change in code. If there is an ADR,
link it. If this touches a boundary listed in CLAUDE.md and there is no ADR yet,
say so -- that is a discussion, not a blocker. -->

## What you verified by running it

<!-- Required, and not the same as "tests pass".

Passing tests have described a working system incorrectly here three times: a
mocked Gemini test passed while every live tool call failed, the async refactor
was green while the loop was still blocked, and the queue's tests passed before
the application could enqueue anything at all.

So: what did you actually run? `just smoke`? A live provider call? A migration
against a database with rows in it? "Nothing beyond the suite" is a legitimate
answer for a change that cannot reach those paths -- say that instead of leaving
this blank. -->

## Checklist

- [ ] `just check-all` passes locally
- [ ] Any new guard has been **seen to fail** — a guard nobody has watched fail is untested
- [ ] `Not built:` and `Invariant:` markers still accurate for the code they sit next to
- [ ] Test docstrings state the invariant *and* the consequence of breaking it
- [ ] A boundary change, new dependency, or infrastructure commitment has an ADR
