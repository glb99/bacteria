set dotenv-load

PORT := env("PORT", "8000")
ARGS_TEST := env("_UV_RUN_ARGS_TEST", "")
ARGS_SERVE := env("_UV_RUN_ARGS_SERVE", "")

# The linter and type checker used to be pinned here as `ruff@0.16.2` strings
# and run with `uvx`. They are workspace dev dependencies now, so `uv run` picks
# them out of the lockfile.
#
# The original reason for pinning still holds and is why they are not simply
# unpinned: `uvx ruff` resolves the newest release every time, so an unpinned
# gate turns red between two runs with no commit in between -- which is how it
# stayed red here long enough for everyone to route around it. The lockfile pins
# them just as hard and adds the part a string constant could not: dependabot
# proposes the bump, and CI runs the new version against the code before anyone
# merges it. A pin nobody tracks only gets bumped when someone notices.


@_:
    just --list


# Run every package's tests
[group('qa')]
test *args:
    just test-agent {{ args }}
    just test-app {{ args }}

# Note this shares the workspace venv, so it does not prove independence by
# itself -- test_package_boundaries.py does that, statically.
#
# `just` uses the last contiguous comment line as a recipe's description, so the
# one-line summary goes immediately above the recipe and the reasoning goes
# above a blank line. Without the blank line `just --list` shows the tail of the
# explanation, which is how this file's listing came to read as fragments.

# Run the agent's tests alone
[group('qa')]
test-agent *args:
    uv run --package bacteria-agent {{ ARGS_TEST }} -m pytest backend/agent/tests {{ args }}

# Run the application's tests alone
[group('qa')]
test-app *args:
    uv run --package bacteria-app {{ ARGS_TEST }} -m pytest backend/app/tests {{ args }}

_cov *args:
    uv run -m coverage {{ args }}

# Run tests and measure coverage
[group('qa')]
@cov:
    just _cov erase
    # The application only. The agent's suite is excluded on purpose --
    # see the note on `source` in pyproject.toml.
    just _cov run -m pytest backend/app/tests
    # The entrypoint import check used to live here as `run -m
    # bacteria.app.entrypoints.asgi`, which quietly stopped being one when asgi.py
    # grew a __main__ block: -m runs the module, so it started a server and hung.
    # It is tests/test_entrypoints.py now.
    just _cov combine
    just _cov report
    just _cov html

# Check lint and formatting. Reports; changes nothing -- see `just fmt`.
[group('qa')]
lint:
    uv run ruff check
    uv run ruff format --check

# Apply what `lint` reports, where it can be applied automatically
[group('qa')]
fmt:
    uv run ruff check --fix
    uv run ruff format

# Run once per clone. `-f` replaces an older hook if one is already installed.

# Install the git pre-commit hook, so lint runs before a commit not after CI
[group('qa')]
hooks:
    uv run prek install -f

# Run every pre-commit hook over the whole tree, not just staged files
[group('qa')]
hooks-all:
    uv run prek run --all-files

# Reads only, so it is safe to point at production -- which is the case it
# exists for. Deliberately not part of `check-all`: the gate judges seeded
# fixtures, in tests/test_evaluation.py, because a gate that depends on what a
# live database happens to contain is not a gate. Those are different claims and
# the report should not be able to be mistaken for the other one.

# Judge the runs recorded in the configured database (ADR 0020)
[group('qa')]
eval *args:
    uv run bacteria-admin eval {{ args }}

# Check types
[group('qa')]
typing:
    uv run ty check --python .venv backend/agent/src backend/app/src

# Catches the class of bug that does not fail a run: an unpinned action, a
# credential left available to a step that does not need it, a
# `pull_request_target` that checks out untrusted code. None of those break CI --
# they break trust in it.

# Lint the GitHub Actions workflows for security mistakes
[group('qa')]
audit-ci:
    uv run zizmor .github/workflows

# Regenerate the console's client from the application's own OpenAPI document.
#
# Two steps rather than one npm script, because the first needs Python and the
# second needs node. The document is dumped from `create_app()` rather than
# fetched from a running server: a step that needed a port, a database and a
# startup wait would not survive being run inside CI or a pre-commit hook.
#
# `frontend/src/api.gen.ts` is committed; the document it came from is not. The
# frontend CI job runs this and fails when the result differs from what was
# committed, which is what stops a renamed response field from reaching a client
# that still expects the old one -- the same shape as the migration drift test.

# Regenerate the console's typed API client
[group('console')]
console-types:
    uv run python scripts/openapi_document.py > frontend/openapi.json
    cd frontend && npm run generate

# Build the console into the package directory the API serves it from.
#
# `npm ci`, not `npm install`: it installs exactly the lockfile and fails when
# `package.json` and the lock disagree, which is the difference between a build
# that is reproducible and one that resolves whatever is newest today. The same
# argument the comment at the top of this file makes about pinning the linter.

# Build the console
[group('console')]
console-build:
    cd frontend && npm ci && npm run build

# Check the console's types and that its client matches the API
[group('console')]
console-check: console-types
    cd frontend && npm run typecheck
    git diff --exit-code frontend/src/api.gen.ts

# `test-agent` is listed explicitly because `cov` does not cover it. Coverage
# measures the application only, deliberately (ADR 0013) -- but "excluded from
# the coverage report" quietly became "not run by the gate", so the agent's
# architectural fitness functions, the tests most worth running before shipping,
# were the ones this recipe skipped.
#
# This is the same set CI runs, in the same order, and that is the point: a gate
# you can only satisfy by pushing is a gate that trains people to push.

# Perform all checks
[group('qa')]
check-all: lint test-agent cov typing audit-ci console-check


# Names the service rather than starting everything in the file, because
# `compose.yml` will gain the application's own services once there is an image
# to run -- and a bare `up` would then start a container of the code you are
# about to edit. Kept out of the recipe body because `just` echoes body comments
# on every run.

# Start Postgres and wait until it is actually accepting queries
[group('db')]
db-up:
    docker compose up -d --wait postgres

# Stop Postgres, keeping its data
[group('db')]
db-down:
    docker compose down

# Stop Postgres and delete its data
[group('db')]
db-reset:
    docker compose down -v
    just db-up
    just migrate

# Apply all pending migrations
[group('db')]
migrate *args="head":
    uv run --package bacteria-app -m alembic -c backend/app/alembic.ini upgrade {{ args }}

# Generate a migration from changes to the models -- always read it before committing
[group('db')]
makemigration message:
    uv run --package bacteria-app -m alembic -c backend/app/alembic.ini revision --autogenerate -m "{{ message }}"

# Undo the last migration
[group('db')]
rollback *args="-1":
    uv run --package bacteria-app -m alembic -c backend/app/alembic.ini downgrade {{ args }}

# Show the migration the database is currently at
[group('db')]
db-version:
    uv run --package bacteria-app -m alembic -c backend/app/alembic.ini current


# Run development server -- migrates first, as a deployment would
[group('run')]
serve: db-up migrate
    uv run {{ ARGS_SERVE }} bacteria-serve

# Run the background worker
[group('run')]
worker *args:
    uv run bacteria-worker {{ args }}

# Migrations run to completion first, then the API and the worker start against
# the same image. Combined explicitly rather than named `compose.override.yml`,
# which Docker Compose would load on its own -- `just db-up` and the test suite
# want the database and nothing else.
#
# This is not a deployment: no TLS, no restart policy, development credentials.
# It exists so the image is known to run all three processes, which a Dockerfile
# otherwise only appears to do.

# Run the whole stack in containers, as one image and three processes
[group('run')]
stack *args:
    docker compose -f compose.yml -f compose.app.yml up --build {{ args }}

# Stop the containerized stack and remove its volumes
[group('run')]
stack-down:
    docker compose -f compose.yml -f compose.app.yml down -v --remove-orphans

# Talk to the agent in a terminal
[group('run')]
agent:
    uv run bacteria-agent

# Starts a server and a worker, issues a credential through the CLI, and makes
# real requests -- because three times here a green suite described a system
# that did not work, each time because the test supplied the thing whose absence
# was the bug. Notably it is the only check that proves a deferred job reaches a
# worker, which no test run can: there is no worker in one.
#
# Assumes the database is up and migrated. Verified to fail: run it with the
# worker stopped and the queue check times out.

# Exercise the real path against a running stack
[group('qa')]
smoke *args:
    uv run python scripts/smoke.py --managed {{ args }}

# Send HTTP request to development server
[group('run')]
req path="" *args:
    @just _http {{ args }} http://127.0.0.1:{{ PORT }}/{{ path }}

_http *args:
    uvx --from httpie http {{ args }}

# Open development server in web browser
[group('run')]
browser:
    uv run -m webbrowser -t http://127.0.0.1:{{ PORT }}


# Update dependencies
[group('lifecycle')]
update:
    uv sync --upgrade

# Ensure project virtualenv is up to date
[group('lifecycle')]
install:
    uv sync

# Remove temporary files
[group('lifecycle')]
clean:
    rm -rf .venv .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
    find . -type d -name "__pycache__" -exec rm -r {} +

# Recreate project virtualenv from nothing
[group('lifecycle')]
fresh: clean install
