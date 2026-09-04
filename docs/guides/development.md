# Development

The command reference. [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md) has the
workflow around them.

```bash
just test            # both suites; test-agent and test-app run them separately
just cov             # application coverage, entrypoints omitted
just lint            # ruff check + format
just typing          # ty
just audit-ci        # zizmor over the workflows
just console-check   # console types, and that the generated client has not drifted
just console-build   # and that the bundle actually builds, which typing alone misses
just check-all       # all of the above
```

`just check-all` is what CI runs, apart from a handful of recorded exceptions —
things needing a Docker daemon, a migrated database, or minutes rather than
seconds. A check that exists only in CI is one people meet by being rejected by
it, so the exceptions are not left to be noticed: `backend/app/tests/test_ci_gates.py`
compares the two lists and fails on any difference that has not been written
down with its reason.

```bash
just smoke           # start a server and a worker, issue a key, make real requests
```

The one check the suite structurally cannot make. It proves a deferred job is
picked up by a worker in another process — there is no worker in a test run, and
this project has already shipped a queue whose tests passed before the
application could enqueue anything at all.

```bash
just stack           # the whole thing in containers: migrate, then API + worker
just stack-smoke     # ... and run the smoke checks against it. What CI gates.
just stack-stop      # stop the app containers, keep the database
just stack-down      # also removes the Postgres volume `just db-up` shares
```

One image, three processes. Not a deployment — no TLS, no restart policy,
development credentials — but proof the image runs all of them against a real
database, and the console is built inside it rather than copied from whatever
the working tree happened to hold.

`just stack-smoke` is the gate on that, and it exists because nothing built this
image before. `fastapi deploy` never reads the `Dockerfile`; the platform builds
with its own `uv sync`. So this is a second packaging path, and an unbuilt one
is not the exit route it is meant to be.

```bash
just makemigration "add whatever"   # generate from model changes — read it before committing
just migrate                        # apply
just db-version                     # what the database is at
```

```bash
just agent           # run the agent standalone in a terminal
just serve           # migrate, then run the web service
```

