"""The entrypoints must at least import.

Entrypoints are omitted from coverage, on the rule that they hold configuration
and no logic. That makes a plain import the only check they get, and it is worth
having: a bad import here is a process that will not start, and nothing else in
the suite would notice.

This used to live in the Justfile as `coverage run -m fastpaip.entrypoints.asgi`,
which stopped being an import check the moment `asgi.py` grew a `__main__`
block — `-m` runs the module, so the command started a server and hung instead
of failing. A test is the right home for it.
"""

import importlib


def test_the_asgi_entrypoint_imports_and_exposes_an_app():
    """`app` is what a deployment's ASGI server looks for by name."""
    asgi = importlib.import_module("fastpaip.entrypoints.asgi")

    assert asgi.app.routes
    assert callable(asgi.main)


def test_the_admin_and_worker_entrypoints_import():
    """Both are console scripts, so a broken import is only found on first run."""
    for name in ("fastpaip.entrypoints.cli", "fastpaip.entrypoints.queue_worker"):
        assert importlib.import_module(name) is not None
