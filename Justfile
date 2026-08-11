set dotenv-load

PORT := env("PORT", "8000")
ARGS_TEST := env("_UV_RUN_ARGS_TEST", "")
ARGS_SERVE := env("_UV_RUN_ARGS_SERVE", "")

# Pinned, because `uvx ruff` resolves the newest release every time and these
# are gates. An unpinned linter means `check-all` can turn red between two runs
# with no commit in between -- which is how it stayed red here long enough for
# everyone to route around it. Bump deliberately, with the diff in its own
# commit.
RUFF := "ruff@0.16.2"
TY := "ty@0.0.70"


@_:
    just --list


# Run every package's tests
[group('qa')]
test *args:
    just test-agent {{ args }}
    just test-app {{ args }}

# Run the agent's tests alone. Note this shares the workspace venv, so it does
# not prove independence by itself -- test_package_boundaries.py does, statically.
[group('qa')]
test-agent *args:
    uv run --package bacteria {{ ARGS_TEST }} -m pytest packages/bacteria/tests {{ args }}

# Run the application's tests alone
[group('qa')]
test-app *args:
    uv run --package fastpaip {{ ARGS_TEST }} -m pytest packages/fastpaip/tests {{ args }}

_cov *args:
    uv run -m coverage {{ args }}

# Run tests and measure coverage
[group('qa')]
@cov:
    just _cov erase
    # The application only. The agent's suite is excluded on purpose --
    # see the note on `source` in pyproject.toml.
    just _cov run -m pytest packages/fastpaip/tests
    # The entrypoint import check used to live here as `run -m
    # fastpaip.entrypoints.asgi`, which quietly stopped being one when asgi.py
    # grew a __main__ block: -m runs the module, so it started a server and hung.
    # It is tests/test_entrypoints.py now.
    just _cov combine
    just _cov report
    just _cov html

# Check lint and formatting. Reports; changes nothing -- see `just fmt`.
[group('qa')]
lint:
    uvx {{ RUFF }} check
    uvx {{ RUFF }} format --check

# Apply what `lint` reports, where it can be applied automatically
[group('qa')]
fmt:
    uvx {{ RUFF }} check --fix
    uvx {{ RUFF }} format

# Judge the runs recorded in the configured database (ADR 0020)
#
# Reads only, so it is safe to point at production -- which is the case it
# exists for. Deliberately not part of `check-all`: the gate judges seeded
# fixtures, in tests/test_evaluation.py, because a gate that depends on what a
# live database happens to contain is not a gate. Those are different claims and
# the report should not be able to be mistaken for the other one.
[group('qa')]
eval *args:
    uv run fastpaip-admin eval {{ args }}

# Check types
[group('qa')]
typing:
    uvx {{ TY }} check --python .venv packages/bacteria/src packages/fastpaip/src

# Perform all checks
#
# `test-agent` is listed explicitly because `cov` does not cover it. Coverage
# measures the application only, deliberately (ADR 0013) -- but "excluded from
# the coverage report" quietly became "not run by the gate", so the agent's
# architectural fitness functions, the tests most worth running before shipping,
# were the ones this recipe skipped.
[group('qa')]
check-all: lint test-agent cov typing


# Start Postgres and wait until it is actually accepting queries
[group('db')]
db-up:
    docker compose up -d --wait

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
    uv run --package fastpaip -m alembic -c packages/fastpaip/alembic.ini upgrade {{ args }}

# Generate a migration from changes to the models -- always read it before committing
[group('db')]
makemigration message:
    uv run --package fastpaip -m alembic -c packages/fastpaip/alembic.ini revision --autogenerate -m "{{ message }}"

# Undo the last migration
[group('db')]
rollback *args="-1":
    uv run --package fastpaip -m alembic -c packages/fastpaip/alembic.ini downgrade {{ args }}

# Show the migration the database is currently at
[group('db')]
db-version:
    uv run --package fastpaip -m alembic -c packages/fastpaip/alembic.ini current


# Run development server -- migrates first, as a deployment would
[group('run')]
serve: db-up migrate
    uv run {{ ARGS_SERVE }} fastpaip-serve

# Run the background worker
[group('run')]
worker *args:
    uv run fastpaip-worker {{ args }}

# Talk to the agent in a terminal
[group('run')]
agent:
    uv run bacteria

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
