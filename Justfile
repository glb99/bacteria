set dotenv-load

PORT := env("PORT", "8000")
ARGS_TEST := env("_UV_RUN_ARGS_TEST", "")
ARGS_SERVE := env("_UV_RUN_ARGS_SERVE", "")


@_:
    just --list


# Run every package's tests
[group('qa')]
test *args:
    just test-agent {{ args }}
    just test-app {{ args }}

# Run the agent's tests alone — proves bacteria stands without the application
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

# Run linters
[group('qa')]
lint:
    uvx ruff check
    uvx ruff format

# Check types
[group('qa')]
typing:
    uvx ty check --python .venv packages/bacteria/src packages/fastpaip/src

# Perform all checks
[group('qa')]
check-all: lint cov typing


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
