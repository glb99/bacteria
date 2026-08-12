# Contributing

## Before writing code

**Discuss first if the change touches a boundary.** The boundaries are listed in
[`CLAUDE.md`](CLAUDE.md) and, for the agent, in
[`packages/bacteria/CLAUDE.md`](packages/bacteria/CLAUDE.md). A change that
crosses one, adds a dependency, or commits to infrastructure gets an
[ADR](packages/bacteria/docs/adr/) before it gets an implementation — the record
is the deliverable, not paperwork attached to one.

Small internal changes need none of that ceremony. Fixing a bug inside a module
that keeps its contract is just a pull request.

## Setup

Needs Python 3.13+ ([`.python-version`](.python-version) pins it),
[uv](https://docs.astral.sh/uv/), [just](https://just.systems/), and Docker.

```bash
cp .env.example .env
```

```bash
just db-up && just install && just migrate && just hooks
```

`just hooks` installs the git pre-commit hook. Without it you will discover
formatting problems in CI instead of before the commit.

**Postgres must be running for almost anything.** Without it the migration tests
skip — loudly — and `just serve` fails. There is no SQLite fallback anywhere, and
[the README explains why](README.md) it was removed rather than kept as a fast
path.

## The checks

```bash
just check-all
```

That runs lint, the agent's tests, the application's tests under coverage, the
type checker, and the workflow security audit. It is the same set CI runs, in the
same order, deliberately: a gate you can only satisfy by pushing is a gate that
trains people to push.

Individually: `just lint`, `just fmt`, `just typing`, `just test`, `just cov`,
`just audit-ci`. `just --list` shows everything.

## Testing

**The bar for a test is: would its silent violation cause a real bug?** If yes it
is a load-bearing invariant and gets a test that fails when the invariant breaks.
If it is a judgment call with no runtime behaviour — "we chose X because Y was
premature" — it gets an ADR and no test.

There is no coverage gate on the agent, on purpose
([ADR 0013](packages/bacteria/docs/adr/0013-test-load-bearing-invariants-only.md)).
Do not add one without reversing that decision deliberately.

**Test docstrings state the invariant and the consequence of breaking it.** A test
whose name and body say the same thing twice is missing the point.

**Passing tests are not evidence that something works.** This has been true here
repeatedly, not theoretically: a mocked Gemini test passed while every live tool
call failed; the async refactor was green while the loop was still blocked. For
anything touching a provider API or a real process boundary, exercise the real
path. `just smoke` does it for the HTTP surface.

**Prove a new guard can fail.** The migration drift test was checked by adding a
field without a migration and watching it break. A guard nobody has seen fail is a
guard nobody has tested.

## Conventions

These are mostly descriptions of what the repository already does. They are
written down because they were previously only inferable from `git log`.

### Commits

Imperative, and stating the **change in behaviour** rather than the change in
code. Cite the ADR when there is one.

```
Stop re-reading the whole session to build a value nobody reads (ADR 0023)
Scope memory to a user, and name the rule that selects it (ADR 0021, 0022)
Print the key id that revoke-key actually wants
```

Not `fix: memory bug`, and not a conventional-commits prefix. The subject line is
the one piece of documentation guaranteed to be read, so it carries the finding
rather than a category.

Keep unrelated changes in separate commits. The line-ending normalization in
[`.gitattributes`](.gitattributes) is separate from the scaffolding around it for
exactly this reason.

### Branches

Kebab-case topic nouns. No `feature/` or `fix/` prefixes — the branch is named
after the thing being changed, not its shape.

```
memory-proposals    tests-on-postgres    transcript-ordering
```

### Naming

| Thing | Rule |
|---|---|
| Modules | Named for what they *own*, not what they contain. `access.py`, `retrieval.py`, `approval.py` — never `utils.py` or `helpers.py`. |
| Workflows | Kebab-case, verb-first: `test.yml`, `pre-commit.yml`. |
| Compose files | `compose.yml` is shared; anything else is explicitly combined with `-f`. |
| Migrations | Alembic's generated slug, kept descriptive: `unique_transcript_position_per_session`. |
| Env vars | `FASTPAIP_*` for this application's settings, unprefixed for provider SDK credentials. The two are read by different things — see [`.env.example`](.env.example) and [`core/settings.py`](packages/fastpaip/src/fastpaip/core/settings.py). |

### Versions

`bacteria` carries real semver: it is the vendorable half, declaring protocols
other code implements, so a consumer needs to know which shape it was written
against. Pre-1.0, breaking changes to an implementor go in the minor.

`fastpaip` stays at `"0"`. Nothing consumes it — it is a deployed application and
its releases are commits.

### Comments and docstrings

**Comments explain why, never what.** `# increment the counter` is worthless.
"Bound as a default argument, because a bare closure would capture the loop
variable" is not.

**Record the rejected alternative.** Where a plausible simpler approach was tried
and failed, say so — otherwise it gets tried again. Several docstrings here exist
only to do that; keep them accurate rather than tidy.

Two grep-discoverable markers are load-bearing:

```bash
grep -rn "Not built:" packages/*/src   # a deliberate gap: what, why, and where it goes
grep -rn "Invariant:" packages/*/src   # an enforced, tested property
```

A `Not built:` block describing something that now exists, or an `Invariant:` with
no test behind it, is worse than no marker at all — it is a claim a reader has no
reason to doubt.

## Pull requests

1. One concern per pull request.
2. `just check-all` green locally before pushing.
3. Say what you verified by running, not only what the tests cover.
4. If you added or closed a gap, update the marker in the code — not just the
   description.
