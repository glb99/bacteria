"""Serving a built console without swallowing the API.

The mount is three lines and the risk is entirely in one property: a mount at
``/`` matches every path no earlier route claimed. Get the order wrong and every
API route 404s through the static handler while still appearing in `/docs`,
which is a failure that looks like a client bug from every angle.
"""

import re

import pytest
from fastapi.testclient import TestClient

from bacteria.app.views import CONSOLE_DIR, create_app


@pytest.fixture(name="console")
def _console(tmp_path):
    """A directory standing in for a built frontend."""
    (tmp_path / "index.html").write_text("<title>console</title>", encoding="utf-8")
    (tmp_path / "app.js").write_text("// built", encoding="utf-8")
    return tmp_path


def test_the_console_shadows_no_route_the_api_declares(console, backend_options):
    """Every declared route must still reach the router with a console mounted.

    Enumerated from the OpenAPI schema rather than listed, for the reason
    `test_chat_access.py` gives about the same mistake: a hand-written list only
    asserts about routes somebody remembered, and the failure being guarded
    against is a route added *after* the mount — which by definition nobody
    remembered to add here either. The first version of this test hardcoded
    three paths and asserted one that did not exist on the branch it ran on.

    A `404` is the tell. Reaching the router gives `401` for everything behind a
    credential, `200` for `/health`, and `422` for a body that will not parse —
    all of which mean the request arrived. Only the static handler answers a
    declared path with `404`.
    """
    app = create_app(console_dir=console)
    with TestClient(app, backend_options=backend_options) as client:
        schema = client.app.openapi()
        checked = 0

        for path, operations in schema["paths"].items():
            concrete = re.sub(r"\{[^}]+\}", "placeholder", path)
            for method in operations:
                response = client.request(method.upper(), concrete, json={})
                assert response.status_code != 404, (
                    f"{method.upper()} {path} was answered by the console mount, not by the router"
                )
                checked += 1

        assert checked >= 10, f"only {checked} routes were reached"
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/openapi.json").status_code == 200


def test_a_built_console_is_served_at_the_root(console, backend_options):
    """`/` has to be the console, because that is the URL a person types."""
    app = create_app(console_dir=console)
    with TestClient(app, backend_options=backend_options) as client:
        index = client.get("/")

        assert index.status_code == 200
        assert "console" in index.text
        assert client.get("/app.js").status_code == 200


def test_nothing_is_mounted_without_a_built_console(tmp_path, backend_options):
    """A source checkout that never built a frontend must still serve the API.

    Silent rather than warned about: this is the ordinary state of a fresh
    clone, and a warning that fires when nothing is wrong is one people learn to
    scroll past.
    """
    app = create_app(console_dir=tmp_path)
    with TestClient(app, backend_options=backend_options) as client:
        assert client.get("/").status_code == 404
        assert client.get("/health").status_code == 200


def test_a_directory_without_an_index_is_not_mounted(tmp_path, backend_options):
    """Existing is not the same as being a console.

    A `dist/` left behind by a failed or interrupted build has files in it and
    no `index.html`. Mounting on directory existence alone would serve that,
    and `/` would answer 404 through a handler that had claimed every path —
    taking the API down with it for the sake of a directory nobody meant.
    """
    (tmp_path / "app.js").write_text("// half a build", encoding="utf-8")

    app = create_app(console_dir=tmp_path)
    with TestClient(app, backend_options=backend_options) as client:
        assert client.get("/app.js").status_code == 404
        assert client.post("/chat/sessions", json={}).status_code == 401


def test_the_default_location_is_inside_the_installed_package():
    """The console ships as package data, so it cannot depend on the cwd.

    A path relative to the working directory resolves one way for `just serve`
    at the repository root and another for a container started elsewhere — the
    two-mechanisms failure `load_env_file` documents. This asserts the default
    is anchored to the package itself, which is the property that makes it
    identical in development and in production.
    """
    package_root = CONSOLE_DIR.parent

    assert (package_root / "views.py").is_file()
    assert CONSOLE_DIR.name == "console"
