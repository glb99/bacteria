"""Exercise the real path: a running server, a real worker, a real database.

Why this exists as a script rather than as more tests. Three times in this
project a green suite described a system that did not work: a mocked Gemini test
passed while every live tool call failed; the async refactor was green while the
loop was still blocked; and the queue's tests passed before the application could
enqueue anything at all. Each was invisible for the same reason -- the test
supplied the thing whose absence was the bug.

So nothing here is faked. The server is the console script a deployment runs, on
a real socket. The worker is a second process. The credential is one an operator
issued through the CLI. The assertions below are the ones that would have caught
those three.

What it deliberately does not cover: an agent turn. That needs a model provider,
and the honest options are billing a vendor from CI or injecting a fake -- which
would mean production code carrying a seam that exists only for this script. The
turn is the one path still verified by hand.

Run it against a stack you started yourself:

    uv run python scripts/smoke.py --base-url http://127.0.0.1:8000 --key fp_...

or let it start and stop everything itself, which is what CI does:

    uv run python scripts/smoke.py --managed

or check a deployment that is already running, after it lands:

    uv run python scripts/smoke.py --deployed --base-url https://...

That last mode starts nothing and runs a narrower set — see
:func:`run_deployed_checks` for what it leaves out and why. It still needs
`BACTERIA_DATABASE_URL` for the same database the deployment uses, because the
one thing worth asserting after a deploy — that a worker is draining the queue —
has no route that reports it.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
import time
from typing import Any, Iterator

import httpx
import psycopg

from bacteria.app.auth import keys

# Long enough to absorb a cold start on a CI runner, short enough that a hung
# process fails the job rather than burning the timeout.
STARTUP_TIMEOUT = 60.0
JOB_TIMEOUT = 60.0


class SmokeFailure(AssertionError):
    """A check failed. Carries what was expected, because a bare assert in a CI
    log tells you a line number and nothing about the system."""


def check(condition: bool, description: str, detail: Any = "") -> None:
    if not condition:
        raise SmokeFailure(f"{description}\n    got: {detail!r}")
    print(f"  ok  {description}")


def psycopg_dsn(database_url: str) -> str:
    """Strip SQLAlchemy's dialect prefix, as `core.jobs` does for the same reason."""
    return database_url.replace("+psycopg", "", 1)


@contextlib.contextmanager
def background(name: str, argv: list[str]) -> Iterator[subprocess.Popen]:
    """Run a console script, and make sure its output is seen if it dies.

    Output is inherited rather than piped. A piped process that fills its buffer
    blocks forever, and the failure looks like a timeout rather than a crash --
    which is the wrong thing to be debugging at 2am in a CI log.
    """
    print(f"--> starting {name}: {' '.join(argv)}")
    process = subprocess.Popen(argv)
    try:
        yield process
    finally:
        print(f"--> stopping {name}")
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()


def wait_for_health(base_url: str, process: subprocess.Popen | None) -> None:
    """Poll /health until the server answers, or the server exits.

    Checks the process too. Without that, a server that failed to bind -- or one
    that hit the Windows ProactorEventLoop problem `core/platform.py` exists for
    -- would be reported as a timeout, which names the symptom and hides the
    cause.
    """
    deadline = time.monotonic() + STARTUP_TIMEOUT
    # What the last attempt actually got, so the failure can say. "Did not
    # answer within 60s" is true of a server that is down and of one that
    # answered 404 sixty times, and those are not the same problem: the first
    # sent nothing, the second is running perfectly and was asked the wrong
    # question. A deployed URL with a trailing slash produces the second --
    # `//health` is a 404, not a redirect -- and reading it as a timeout sends
    # you to look at the deployment instead of at the variable.
    last = "nothing was tried"
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise SmokeFailure(f"server exited during startup with code {process.returncode}")
        try:
            response = httpx.get(f"{base_url}/health", timeout=2.0)
            if response.status_code == 200:
                return
            last = f"HTTP {response.status_code}"
        except httpx.TransportError as error:
            last = f"{type(error).__name__}: {error}"
        time.sleep(0.5)
    raise SmokeFailure(
        f"{base_url}/health did not answer 200 within {STARTUP_TIMEOUT}s; last: {last}"
    )


def admin(*args: str) -> subprocess.CompletedProcess:
    """Run `bacteria-admin` and, on failure, say what it actually said.

    **`check=True` was worse than useless here.** It raises a
    ``CalledProcessError`` whose message is the argv and an exit code, while the
    child's stdout and stderr sit captured on the exception where nothing prints
    them. So a smoke run against a deployment reported "returned non-zero exit
    status 1" and a traceback through `subprocess`, about a command whose own
    error message explained the problem in one line and was thrown away.

    That is the failure this whole script exists to avoid making: a gate that
    fails without saying why sends someone to read the gate instead of the
    system.
    """
    result = subprocess.run(
        [sys.executable, "-m", "bacteria.app.entrypoints.cli", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SmokeFailure(
            f"bacteria-admin {' '.join(args)} exited {result.returncode}"
            f"\n    stdout: {result.stdout.strip() or '(empty)'}"
            f"\n    stderr: {result.stderr.strip() or '(empty)'}"
        )
    return result


def issue_key(principal: str) -> str:
    """Mint a credential the way an operator does, and parse it off stdout.

    Not inserted into the table directly. The point is that the CLI a human runs
    produces a token the HTTP layer accepts -- those are different code paths and
    the hashing between them is exactly where they could disagree.
    """
    result = admin("issue-key", principal, "--label", "smoke")
    for token in result.stdout.split():
        if token.startswith("fp_"):
            return token
    raise SmokeFailure(f"no key in issue-key output:\n{result.stdout}\n{result.stderr}")


def revoke_key(token: str) -> None:
    """Retire a credential this script minted, by the id inside its token.

    `revoke-key` refuses a whole key on purpose -- it is most often run because
    one leaked, and taking the token would put the secret in shell history at
    exactly that moment. So the id is split out here rather than passed through.
    """
    key_id = keys.split(token)
    if key_id is None:
        raise SmokeFailure(f"could not split a key id out of {token[:12]}...")
    admin("revoke-key", key_id[0])


def check_auth(base_url: str, key: str) -> None:
    print("\n[auth] every failure looks identical to a client")
    anonymous = httpx.post(f"{base_url}/chat/sessions", timeout=10.0)
    check(anonymous.status_code == 401, "no credentials is 401", anonymous.status_code)

    for label, token in [("malformed", "not-a-key"), ("unknown", "fp_deadbeef_nope")]:
        response = httpx.post(
            f"{base_url}/chat/sessions",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        check(response.status_code == 401, f"{label} credential is 401", response.status_code)

    healthy = httpx.get(f"{base_url}/health", timeout=10.0)
    check(healthy.status_code == 200, "/health needs no credential", healthy.status_code)


def check_ownership(base_url: str, key: str, other_key: str) -> str:
    print("\n[ownership] a session id is not permission to read it")
    headers = {"Authorization": f"Bearer {key}"}
    created = httpx.post(f"{base_url}/chat/sessions", headers=headers, timeout=10.0)
    check(created.status_code == 201, "session created", created.status_code)
    session_id = created.json()["session_id"]

    stranger = httpx.get(
        f"{base_url}/chat/sessions/{session_id}/transcript",
        headers={"Authorization": f"Bearer {other_key}"},
        timeout=10.0,
    )
    # 404 and not 403: a 403 would confirm the session exists, which turns an id
    # into an oracle for enumeration.
    check(
        stranger.status_code == 404,
        "another principal's session is 404, not 403",
        stranger.status_code,
    )

    absent = httpx.get(
        f"{base_url}/chat/sessions/does-not-exist/transcript", headers=headers, timeout=10.0
    )
    check(absent.status_code == 404, "a missing session is the same 404", absent.status_code)
    return session_id


def check_memory(base_url: str, key: str, session_id: str) -> None:
    print("\n[memory] the owner writes it, and can read back why")
    headers = {"Authorization": f"Bearer {key}"}
    written = httpx.put(
        f"{base_url}/chat/sessions/{session_id}/memory/tone",
        headers=headers,
        json={"value": "terse", "reason": "smoke test asked for it"},
        timeout=10.0,
    )
    check(written.status_code == 200, "memory written", written.status_code)

    listed = httpx.get(
        f"{base_url}/chat/sessions/{session_id}/memory", headers=headers, timeout=10.0
    )
    entries = listed.json()
    check(
        any(e["key"] == "tone" and e["value"] == "terse" for e in entries),
        "memory reads back",
        entries,
    )
    check(all(e["reason"] for e in entries), "every entry carries its reason", entries)

    httpx.delete(
        f"{base_url}/chat/sessions/{session_id}/memory/tone", headers=headers, timeout=10.0
    )
    after = httpx.get(
        f"{base_url}/chat/sessions/{session_id}/memory", headers=headers, timeout=10.0
    ).json()
    check(not any(e["key"] == "tone" for e in after), "memory deleted", after)


def check_inline_ingestion(base_url: str, key: str) -> None:
    print("\n[ingestion] nothing is dropped silently")
    response = httpx.post(
        f"{base_url}/ingestion/batches",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "source": "smoke",
            "records": [
                {"external_id": "s-1", "name": "Ada Lovelace"},
                {"name": "no id"},
                {"external_id": "s-1", "name": "duplicate"},
            ],
        },
        timeout=30.0,
    )
    check(response.status_code == 201, "batch accepted", response.status_code)
    body = response.json()
    check(body["accepted"] == 1, "one record accepted", body)
    check(len(body["rejected"]) == 2, "two records rejected, not counted away", body)
    # The index is what makes two identical bad records distinguishable.
    check(
        sorted(r["index"] for r in body["rejected"]) == [1, 2],
        "rejections carry their position",
        body,
    )


def check_deferred_ingestion(base_url: str, key: str, database_url: str) -> None:
    """The check the test suite structurally cannot make.

    `just test` proves the queue works and proves the route returns a job id. It
    cannot prove a worker in another process picks the job up, because there is
    no worker in a test run -- which is exactly the shape of the bug this project
    already had once, where the queue's tests passed before the application could
    enqueue at all.
    """
    print("\n[queue] a deferred job actually reaches a worker")
    response = httpx.post(
        f"{base_url}/ingestion/batches:defer",
        headers={"Authorization": f"Bearer {key}"},
        json={"source": "smoke-deferred", "records": [{"external_id": "d-1", "name": "Deferred"}]},
        timeout=30.0,
    )
    check(response.status_code == 202, "deferral accepted with 202, not 201", response.status_code)
    job_id = response.json()["job_id"]

    # Read the queue directly. There is no route reporting a job's outcome --
    # that is a recorded gap in ingestion/views.py, and this script is not the
    # place to paper over it.
    deadline = time.monotonic() + JOB_TIMEOUT
    status = None
    with psycopg.connect(psycopg_dsn(database_url)) as connection:
        while time.monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status FROM procrastinate_jobs WHERE id = %s", (job_id,))
                row = cursor.fetchone()
            connection.commit()
            status = row[0] if row else None
            if status in ("succeeded", "failed"):
                break
            time.sleep(0.5)
    check(status == "succeeded", f"job {job_id} was drained by the worker", status)


def check_chat_cli(database_url: str) -> None:
    """Start the chat command as its own process and let it reach EOF.

    The suite cannot run a console script at all, so nothing else in this
    project proves this entrypoint composes: that its settings resolve, that it
    reaches the database, that it opens procrastinate's pool, and that it writes
    a session row. Each of those is wiring rather than logic, which is precisely
    the category `entrypoints/` is exempt from unit-testing and therefore the
    category only this script can defend.

    **This does not cover a turn**, for the reason in the module docstring — a
    turn needs a model provider. So it would not have caught the bug that
    prompted it: `bacteria-admin chat` shipped without opening the queue, and
    that fails at the deferral, which is after the model has answered. The guard
    for *that* is `test_a_turn_refuses_before_the_model_when_it_cannot_enqueue`,
    which moved the failure in front of the model call where a test can reach
    it. This check is the weaker, complementary half: it proves the process
    starts at all.

    Extraction is turned on for the run so the header states the worker
    requirement. A person running this command to see what extraction produces
    and getting no proposals is the expected result of forgetting `just worker`,
    and nothing else would tell them.
    """
    print("\n[cli] the chat command starts, connects, and opens the job queue")

    # A key is issued for this principal first, and the token is thrown away.
    # `chat` now refuses a principal no key was ever issued to, because a
    # mistyped one produces a session owned by nobody -- unreachable over HTTP
    # forever, since no credential resolves to it.
    #
    # This script was creating exactly that on every CI run: `smoke-cli` had no
    # key, only `smoke-principal` and `smoke-stranger` did. So the guard's first
    # catch was a real orphan rather than a hypothetical one, and the fix is
    # here rather than in the guard -- issuing before chatting is what an
    # operator does.
    issue_key("smoke-cli")

    result = subprocess.run(
        [sys.executable, "-m", "bacteria.app.entrypoints.cli", "chat", "smoke-cli"],
        input="",
        capture_output=True,
        text=True,
        env={**os.environ, "BACTERIA_MEMORY_EXTRACTION_ENABLED": "true"},
    )
    check(
        result.returncode == 0,
        "the chat command started and exited cleanly",
        (result.returncode, result.stderr[-400:]),
    )
    check(
        "extraction: on" in result.stdout,
        "extraction being on says a worker is needed",
        result.stdout,
    )

    session_id = ""
    for line in result.stdout.splitlines():
        if line.startswith("new session:"):
            session_id = line.split(":", 1)[1].strip()
    check(bool(session_id), "the command reported a session id", result.stdout)

    # Read back rather than trusting stdout: printing an id and storing one are
    # different things, and this entrypoint is new enough that the difference is
    # worth an assertion rather than an assumption.
    with psycopg.connect(psycopg_dsn(database_url)) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT user_id FROM chat_session WHERE session_id = %s", (session_id,))
        row = cursor.fetchone()
    check(
        row is not None and row[0] == "smoke-cli", "the session was written, not just printed", row
    )


def run_checks(base_url: str, database_url: str) -> None:
    key = issue_key("smoke-principal")
    other_key = issue_key("smoke-stranger")
    check_auth(base_url, key)
    session_id = check_ownership(base_url, key, other_key)
    check_memory(base_url, key, session_id)
    check_inline_ingestion(base_url, key)
    check_deferred_ingestion(base_url, key, database_url)
    check_chat_cli(database_url)


def check_console_is_served(base_url: str) -> None:
    """The deployed application serves a built console at its root.

    **A guard for a failure that is deliberately silent everywhere else.**
    `views.py` mounts nothing when there is no `index.html`, on purpose, because
    an unbuilt checkout is the ordinary state of a fresh clone. In production
    that same silence means the console directory shipped empty -- `/` answers
    404, every API route keeps working, and the deployment looks healthy from
    every other check in this file.

    **Polls, and that is not defensive padding.** `fastapi deploy` prints "your
    app is ready" when its build is ready, which is not the same instant the new
    revision starts serving traffic. Asked once, this check failed a second
    after that line appeared -- against the *previous* revision, which genuinely
    had no console -- and reported a packaging fault that had already been fixed.

    So this doubles as the wait for the rollout, and it is the only check here
    that can serve as one. `check_auth` and `check_deferred_ingestion` answer
    identically on either revision, so neither can tell you which one you are
    talking to. That makes this the first check to run and the one that decides
    whether the rest are describing what was just deployed.

    Deployed only, not in `run_checks`. A local `just smoke` runs against a
    checkout that may legitimately have no console, and a gate that fails for
    that would be one people learn to run around.
    """
    print("\n[console] a built console is served at the root")
    deadline = time.monotonic() + STARTUP_TIMEOUT
    last = "nothing was tried"

    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{base_url}/", timeout=10.0, follow_redirects=True)
        except httpx.TransportError as error:
            last = f"{type(error).__name__}: {error}"
        else:
            # Asserted on the marker the build leaves rather than on any text,
            # so that restyling the page cannot fail a deploy. What is being
            # checked is that a *build* is present, not what it says.
            if response.status_code == 200 and 'src="/assets/' in response.text:
                check(True, f"a built console is served at {base_url}/")
                return
            last = f"HTTP {response.status_code}"
        time.sleep(2.0)

    check(
        False,
        f"a built console was served at {base_url}/ within {STARTUP_TIMEOUT}s",
        last,
    )


def run_deployed_checks(base_url: str, database_url: str) -> None:
    """The subset worth running against a deployment, after it lands.

    Narrower than :func:`run_checks` on purpose, and the omissions are the
    argument. ``check_chat_cli`` runs a local process and says nothing about
    what was deployed. ``check_ownership`` and ``check_memory`` write a
    conversation and its memory into the production database on every deploy,
    which is a cost with no matching finding — the routes they cover are
    already covered by the suite against real Postgres.

    What survives is what the suite structurally cannot answer about a
    *deployment*: that the process is serving, that authentication is on, and
    that something is draining the queue.

    That last one is the reason this exists. Six failures in a row shipped
    silently here — four packaging, two configuration — and the last was
    `BACTERIA_RUN_WORKER_IN_API` never reaching the process, which left the
    service conversing normally while no job was ever consumed. It was found by
    hand, days later. `check_deferred_ingestion` fails in sixty seconds on
    exactly that, and costs no model call, so it can run on every deploy without
    billing a vendor from CI.

    The credential is minted and then retired. A key per deploy that nobody
    revokes is a live credential accumulating in production for a principal only
    CI uses.
    """
    check_console_is_served(base_url)

    key = issue_key("smoke-deploy")
    try:
        check_auth(base_url, key)
        check_deferred_ingestion(base_url, key, database_url)
    finally:
        revoke_key(key)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--deployed",
        action="store_true",
        help="Check a deployment that is already running. Starts nothing, and skips "
        "the checks that would write a conversation into production.",
    )
    parser.add_argument("--key", help="Skip issuing one and use this credential.")
    parser.add_argument(
        "--managed",
        action="store_true",
        help="Start and stop the server and worker. Assumes the database is migrated.",
    )
    args = parser.parse_args()

    # A dashboard and a browser both hand out URLs with a trailing slash, and
    # every request here appends an absolute path -- so one slash makes every
    # call `//health`, which FastAPI answers 404 rather than redirecting.
    # Trimming it is the script's job: the alternative is a variable that has to
    # be typed exactly right to avoid a failure that names the wrong thing.
    base_url = args.base_url.rstrip("/")

    database_url = os.environ.get(
        "BACTERIA_DATABASE_URL", "postgresql+psycopg://bacteria:bacteria@localhost:5432/bacteria"
    )

    try:
        if args.deployed:
            wait_for_health(base_url, process=None)
            run_deployed_checks(base_url, database_url)
        elif not args.managed:
            wait_for_health(base_url, process=None)
            run_checks(base_url, database_url)
        else:
            host, _, port = base_url.removeprefix("http://").partition(":")
            environment = {**os.environ, "HOST": host, "PORT": port or "8000"}
            server = subprocess.Popen(
                [sys.executable, "-m", "bacteria.app.entrypoints.asgi"], env=environment
            )
            try:
                with background(
                    "worker", [sys.executable, "-m", "bacteria.app.entrypoints.queue_worker"]
                ):
                    wait_for_health(base_url, server)
                    run_checks(base_url, database_url)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    server.kill()
    except SmokeFailure as failure:
        print(f"\nFAILED: {failure}", file=sys.stderr)
        return 1

    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
