# One image, three processes. `fastpaip-serve`, `fastpaip-worker`, and
# `fastpaip-admin` are console scripts on the same install, so the API, the queue
# worker, and the operator CLI cannot drift onto different code -- which is the
# failure a separate worker image invites, and it shows up as a job failing to
# deserialize rather than as anything obviously version-shaped.
#
# The command is not set here. `compose.app.yml` supplies it per service,
# because which process this container is is a deployment decision and not a
# property of the build.

FROM python:3.13-slim-bookworm AS base

# Compile to bytecode at install time and copy rather than link out of the cache
# mount, which is the documented uv-in-Docker pairing: the cache does not survive
# into the image, so a link would dangle.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# curl is here for the healthcheck in compose.app.yml and nothing else. It is a
# real cost -- one more package with its own CVE feed -- and the alternative is
# a healthcheck written in Python against the same interpreter the app uses,
# which is the thing being checked. A dependent probe that shares the failure
# mode of its subject reports healthy right up until it cannot run at all.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /uvx /bin/

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

# Dependencies before source, in their own layer, so editing a module does not
# reinstall psycopg. `--no-install-workspace` is what makes that split real: it
# resolves and installs everything the workspace depends on while installing
# neither member, so this layer is invalidated only by the lockfile.
#
# The pyprojects are bind-mounted rather than copied because uv needs to read
# them to resolve, and copying them would put them in the layer and tie its cache
# key to files that change far more often than the dependency set does.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=packages/bacteria/pyproject.toml,target=packages/bacteria/pyproject.toml \
    --mount=type=bind,source=packages/fastpaip/pyproject.toml,target=packages/fastpaip/pyproject.toml \
    uv sync --locked --no-install-workspace --no-dev --package fastpaip

COPY packages/ /app/packages/
COPY pyproject.toml uv.lock /app/
COPY scripts/ /app/scripts/

# Now the members themselves. `--package fastpaip` rather than a bare `uv sync`,
# and that is not a refinement -- the workspace root sets `package = false`, so a
# bare sync installs the root's own dependencies (there are none) and no member
# at all. The image built, started, and had no `fastpaip` module in it. It pulls
# `bacteria` in as a workspace dependency, so naming one member is enough.
#
# `--locked` fails rather than silently re-resolving if uv.lock disagrees with
# the pyprojects, which is the point of building from a lockfile: a build that
# quietly picks different versions than the ones tested is worse than one that
# stops.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package fastpaip

# Non-root, and created before the switch so the venv stays owned by root and
# read-only to the process using it. A compromised worker cannot rewrite the code
# it is running.
RUN useradd --create-home --uid 10001 fastpaip
USER fastpaip

# Alembic is invoked from the package directory, matching alembic.ini's own
# relative paths, and matching how `just migrate` runs it.
WORKDIR /app/packages/fastpaip
