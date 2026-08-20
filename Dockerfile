# One image, three processes. `bacteria-serve`, `bacteria-worker`, and
# `bacteria-admin` are console scripts on the same install, so the API, the queue
# worker, and the operator CLI cannot drift onto different code -- which is the
# failure a separate worker image invites, and it shows up as a job failing to
# deserialize rather than as anything obviously version-shaped.
#
# The command is not set here. `compose.app.yml` supplies it per service,
# because which process this container is is a deployment decision and not a
# property of the build.

# The console is built here rather than copied in, and that is a correctness fix
# rather than a convenience. `.dockerignore` used to let `COPY backend/` pick up
# `backend/app/src/bacteria/app/console/` -- gitignored build output -- so the
# image contained whatever the developer had last built, a stale bundle, or on a
# fresh clone nothing at all. The same class of bug as the deploy workflow's
# `rignore` problem, with the same symptom: `/` answers 404 and every API route
# keeps working, so the deployment looks healthy from every other check.
#
# Its own stage, so node is a build dependency and never ships. `npm ci` for the
# reason `just console-build` gives: it installs the lockfile exactly and fails
# when `package.json` disagrees, where `npm install` resolves whatever is newest.
FROM node:22-slim AS console

WORKDIR /frontend
# The manifests alone first, so editing a component does not reinstall vite.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# `vite.config.ts` writes to `../backend/app/src/bacteria/app/console`, which
# lands at /backend/... in this stage. Not overridden here: the path is where the
# Python package looks, and a second definition of it is a second thing to keep
# in step.
RUN npm run build


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
    --mount=type=bind,source=backend/agent/pyproject.toml,target=backend/agent/pyproject.toml \
    --mount=type=bind,source=backend/app/pyproject.toml,target=backend/app/pyproject.toml \
    uv sync --locked --no-install-workspace --no-dev --package bacteria-app

COPY backend/ /app/backend/
COPY pyproject.toml uv.lock /app/
COPY scripts/ /app/scripts/

# Now the members themselves. `--package bacteria-app` rather than a bare `uv sync`,
# and that is not a refinement -- the workspace root sets `package = false`, so a
# bare sync installs the root's own dependencies (there are none) and no member
# at all. The image built, started, and had no `bacteria.app` module in it. It pulls
# `bacteria-agent` in as a workspace dependency, so naming one member is enough.
#
# `--locked` fails rather than silently re-resolving if uv.lock disagrees with
# the pyprojects, which is the point of building from a lockfile: a build that
# quietly picks different versions than the ones tested is worse than one that
# stops.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package bacteria-app

# After the sync, so a frontend edit does not invalidate the dependency layers.
#
# Into the source tree because `uv sync` installs workspace members editable, so
# this is the directory the installed `bacteria.app` imports from. That is an
# assumption about uv rather than something this file controls, which is why the
# next step checks it instead of trusting it.
# Emptied first, because `COPY backend/` above brings in whatever the developer
# last built. Doing it here rather than in `.dockerignore` is deliberate and the
# comment there says why: that file is uploaded to FastAPI Cloud and read by its
# builder, so excluding the console there took it out of the *deployed* image.
RUN rm -rf /app/backend/app/src/bacteria/app/console

COPY --from=console /backend/app/src/bacteria/app/console/                     /app/backend/app/src/bacteria/app/console/

# Asked of the *installed* package, not of the filesystem. `views.py` mounts
# nothing when `index.html` is absent -- deliberately, because an unbuilt
# checkout is the ordinary state of a clone -- so a console that landed in the
# wrong directory produces an image that starts cleanly, serves every API route,
# and 404s at `/`. That is precisely the failure that shipped six times from the
# other packaging path. Here it is a build error.
RUN python -c "from bacteria.app.views import CONSOLE_DIR; index = CONSOLE_DIR / 'index.html'; assert index.is_file(), f'no console at {CONSOLE_DIR}; the COPY above missed where the package imports from'; print(f'console present: {CONSOLE_DIR}')"

# Non-root, and created before the switch so the venv stays owned by root and
# read-only to the process using it. A compromised worker cannot rewrite the code
# it is running.
RUN useradd --create-home --uid 10001 bacteria
USER bacteria

# Alembic is invoked from the package directory, matching alembic.ini's own
# relative paths, and matching how `just migrate` runs it.
WORKDIR /app/backend/app
