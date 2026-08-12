"""The entrypoints must at least import.

Entrypoints are omitted from coverage, on the rule that they hold configuration
and no logic. That makes a plain import the only check they get, and it is worth
having: a bad import here is a process that will not start, and nothing else in
the suite would notice.

This used to live in the Justfile as `coverage run -m bacteria.app.entrypoints.asgi`,
which stopped being an import check the moment `asgi.py` grew a `__main__`
block — `-m` runs the module, so the command started a server and hung instead
of failing. A test is the right home for it.
"""

import asyncio
import importlib

from bacteria.app.auth import keys
from bacteria.app.core.settings import get_settings
from bacteria.app.entrypoints import cli


def test_the_asgi_entrypoint_imports_and_exposes_an_app():
    """`app` is what a deployment's ASGI server looks for by name."""
    asgi = importlib.import_module("bacteria.app.entrypoints.asgi")

    assert asgi.app.routes
    assert callable(asgi.main)


def test_the_admin_and_worker_entrypoints_import():
    """Both are console scripts, so a broken import is only found on first run."""
    for name in ("bacteria.app.entrypoints.cli", "bacteria.app.entrypoints.queue_worker"):
        assert importlib.import_module(name) is not None


async def test_the_in_api_worker_is_awaited_on_shutdown_not_abandoned(engine, monkeypatch):
    """A worker left running past shutdown strands whatever job it held.

    This is the failure the cancel-and-await exists for, and it is invisible
    without a test. An `asyncio.Task` that is never awaited is destroyed with a
    warning nobody reads, while the job it was mid-way through stays marked
    `doing` in the table -- so it is not picked up by the next worker and does
    not show up as failed either. It is simply gone, and the row looks busy
    forever.

    Exercising the real lifespan rather than calling the helper directly,
    because the bug would live in the shutdown path of the context manager and
    a direct call would skip exactly that.

    Asserting ``cancelled()`` and not ``done()``, which is the whole difference
    between this test and a vacuous one. The first version checked ``done()``
    and passed even with the cancel deleted -- because the connection pool
    closes on the way out either way, which makes an abandoned worker raise and
    finish on its own. Both shapes ended with a finished task; only one of them
    stopped it deliberately, before the pool went away.
    """
    monkeypatch.setenv("BACTERIA_RUN_WORKER_IN_API", "true")
    get_settings.cache_clear()
    asgi = importlib.import_module("bacteria.app.entrypoints.asgi")

    async with asgi.lifespan(asgi.app):
        running = [t for t in asyncio.all_tasks() if t.get_name() == "in-api-procrastinate-worker"]
        assert running, "the worker task was never started"
        worker = running[0]
        assert not worker.done()

    assert worker.done(), "the worker outlived the lifespan that started it"
    assert worker.cancelled(), (
        "the worker finished without being cancelled, so shutdown did not stop it -- "
        "it was abandoned and died when the pool closed under it"
    )
    get_settings.cache_clear()


async def test_no_worker_runs_in_the_api_by_default(engine, monkeypatch):
    """The safe shape is the one you get without asking for it.

    Two processes is the design (`queue_worker.py` says why); one process is the
    concession a single-process platform forces. A default that quietly ran the
    worker in-process would spread that concession to every deployment, including
    the ones already running `bacteria-worker` -- which would then have two
    workers competing for the same queue and no indication anywhere.
    """
    monkeypatch.delenv("BACTERIA_RUN_WORKER_IN_API", raising=False)
    get_settings.cache_clear()
    asgi = importlib.import_module("bacteria.app.entrypoints.asgi")

    async with asgi.lifespan(asgi.app):
        assert not [t for t in asyncio.all_tasks() if t.get_name() == "in-api-procrastinate-worker"]
    get_settings.cache_clear()


async def test_what_issue_key_prints_is_what_revoke_key_accepts(engine, capsys):
    """The two commands have to agree on what a key id is.

    They did not. `issue-key` printed the principal, the label, and the whole
    token; `revoke-key` takes the id, which appeared nowhere in that output. So
    the only value an operator had to copy was the one value revocation rejects,
    and it failed with "no key with id" — which reads as "that key does not
    exist" rather than "you gave me the wrong field".

    Asserted as a round trip rather than as two separate checks on the strings,
    because the defect was the relationship between them and either half alone
    would have looked correct.
    """
    await cli._issue("round-trip", "test")
    printed = dict(
        line.split(":", 1) for line in capsys.readouterr().out.splitlines() if ":" in line
    )
    key_id = printed["key id"].split()[0]

    assert await cli._revoke(key_id) == 0
    assert "revoked" in capsys.readouterr().out


async def test_a_whole_key_is_refused_with_the_field_it_wanted(engine, capsys):
    """Passing the token is the mistake to expect, so it gets a real answer.

    Refused rather than accepted, though the id sits inside it: this command is
    most often run *because* a key leaked, and taking the full token would put
    the secret into shell history at that exact moment. The token is not echoed
    back, for the same reason.
    """
    token = keys.generate().token

    assert await cli._revoke(token) == 1

    out = capsys.readouterr().out
    assert "full key, not a key id" in out
    assert token not in out
