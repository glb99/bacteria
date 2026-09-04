# Testing

**Every test runs on Postgres.** `just db-up` first, or the suite skips — or
fails, under `just cov`; see the note above. There is no SQLite anywhere — not
as a fallback, not as a fast path. It was removed
because it was actively lying: SQLite ignores `DateTime(timezone=True)` and
returns naive datetimes, so every timestamp in the application round-tripped one
way under test and another in production, and no test could see it.

`tests/conftest.py` owns the fixtures. One throwaway database per run, truncated
between tests. Two things in it are load-bearing and non-obvious:

- The `engine` fixture uses `NullPool`, and HTTP tests must request
  `backend_options` and pass it to `TestClient`. An HTTP test drives two event
  loops — pytest-asyncio's and the one `TestClient` opens in its own thread —
  and a psycopg connection shared across them fails with *another command is
  already in progress*.
- Loop selection is a `pytest_asyncio_loop_factories` hook, not a policy, for
  the reason `core/platform.py` gives.

Test docstrings state the invariant *and the consequence of breaking it*. A test
whose name and body say the same thing twice is missing the point.


## The bar for a test

Borrowed from the agent package, and it applies here too: **would its silent
violation cause a real bug?** If yes, it is a load-bearing invariant and gets a
test that fails when the invariant breaks. If it is a judgment call with no
runtime behaviour, it gets an ADR and no test.

The agent package has no coverage gate on purpose
([agent ADR 0013](../../backend/agent/docs/adr/0013-test-load-bearing-invariants-only.md)).
The application does, through `just cov`.
