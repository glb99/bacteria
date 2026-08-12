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
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise SmokeFailure(f"server exited during startup with code {process.returncode}")
        try:
            if httpx.get(f"{base_url}/health", timeout=2.0).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.5)
    raise SmokeFailure(f"server did not answer /health within {STARTUP_TIMEOUT}s")


def issue_key(principal: str) -> str:
    """Mint a credential the way an operator does, and parse it off stdout.

    Not inserted into the table directly. The point is that the CLI a human runs
    produces a token the HTTP layer accepts -- those are different code paths and
    the hashing between them is exactly where they could disagree.
    """
    result = subprocess.run(
        [sys.executable, "-m", "fastpaip.entrypoints.cli", "issue-key", principal, "--label", "smoke"],
        capture_output=True,
        text=True,
        check=True,
    )
    for token in result.stdout.split():
        if token.startswith("fp_"):
            return token
    raise SmokeFailure(f"no key in issue-key output:\n{result.stdout}\n{result.stderr}")


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
    check(stranger.status_code == 404, "another principal's session is 404, not 403", stranger.status_code)

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

    listed = httpx.get(f"{base_url}/chat/sessions/{session_id}/memory", headers=headers, timeout=10.0)
    entries = listed.json()
    check(any(e["key"] == "tone" and e["value"] == "terse" for e in entries), "memory reads back", entries)
    check(all(e["reason"] for e in entries), "every entry carries its reason", entries)

    httpx.delete(f"{base_url}/chat/sessions/{session_id}/memory/tone", headers=headers, timeout=10.0)
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
    check(sorted(r["index"] for r in body["rejected"]) == [1, 2], "rejections carry their position", body)


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


def run_checks(base_url: str, database_url: str) -> None:
    key = issue_key("smoke-principal")
    other_key = issue_key("smoke-stranger")
    check_auth(base_url, key)
    session_id = check_ownership(base_url, key, other_key)
    check_memory(base_url, key, session_id)
    check_inline_ingestion(base_url, key)
    check_deferred_ingestion(base_url, key, database_url)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--key", help="Skip issuing one and use this credential.")
    parser.add_argument(
        "--managed",
        action="store_true",
        help="Start and stop the server and worker. Assumes the database is migrated.",
    )
    args = parser.parse_args()

    database_url = os.environ.get(
        "FASTPAIP_DATABASE_URL", "postgresql+psycopg://fastpaip:fastpaip@localhost:5432/fastpaip"
    )

    try:
        if not args.managed:
            wait_for_health(args.base_url, process=None)
            run_checks(args.base_url, database_url)
        else:
            host, _, port = args.base_url.removeprefix("http://").partition(":")
            environment = {**os.environ, "HOST": host, "PORT": port or "8000"}
            server = subprocess.Popen(
                [sys.executable, "-m", "fastpaip.entrypoints.asgi"], env=environment
            )
            try:
                with background("worker", [sys.executable, "-m", "fastpaip.entrypoints.queue_worker"]):
                    wait_for_health(args.base_url, server)
                    run_checks(args.base_url, database_url)
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
