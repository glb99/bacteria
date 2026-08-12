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

import importlib

from bacteria.app.auth import keys
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
