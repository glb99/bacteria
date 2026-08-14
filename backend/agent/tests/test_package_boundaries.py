"""What this package is allowed to import, and where it may read configuration.

The rule these protect is the one that makes `bacteria.agent` a library rather than a
layer: it depends on nothing from whatever hosts it, and on nothing it has not
declared, and it learns how it is configured from its caller rather than from the
environment. Break any of that and the agent stops being vendorable — which is the
entire premise of the layering.

Static analysis, not an import attempt, and that distinction is the reason this
file exists. In the workspace this package currently lives in, the application
is installed in the same virtualenv, so `import bacteria.app` inside `bacteria/`
would succeed — in development, in CI, in every test run. Nothing would go red.
The failure would surface only when someone vendored this package somewhere
else, which is the furthest possible point from the mistake and the worst place
to diagnose it. Reading the source cannot be fooled by what happens to be
installed.

Checked against this package's own `pyproject.toml` rather than a hardcoded
list of forbidden names. That way the test needs no knowledge of the workspace —
it keeps working when this directory is the whole project — and it catches the
other half of the same mistake: importing something real that nobody declared,
which installs fine here and fails on a clean machine.
"""

import ast
import pathlib
import sys
import tomllib

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = PACKAGE_ROOT / "src"
TESTS = PACKAGE_ROOT / "tests"

DISTRIBUTION_TO_IMPORT = {
    "google-genai": "google",
    "python-dotenv": "dotenv",
}
"""Distributions whose import name differs from the name you install.

Only the exceptions. Anything absent is assumed to import under its own name,
which is true of the rest and stays true for most things added later.
"""

SELF = "bacteria.agent"

NAMESPACE = "bacteria"
"""The namespace both halves of this project share.

Comparing top-level roots alone stopped being enough when they started sharing
it. `bacteria.app` and `bacteria.agent` have the same first component, so a
check that allowed the root `bacteria` would have allowed the agent to import
the application -- the one import these tests exist to forbid -- while still
passing. That is precisely how this guard was defeated by a rename, and why
:func:`_import_key` compares two components inside the namespace and one
outside it.
"""


def _import_key(dotted: str) -> str:
    """Reduce a dotted module path to the unit the allow-list is written in.

    Two components inside the shared namespace, one everywhere else:
    ``bacteria.app.core.db`` -> ``bacteria.app``, and ``anthropic.types`` ->
    ``anthropic``.
    """
    parts = dotted.split(".")
    if parts[0] == NAMESPACE and len(parts) > 1:
        return f"{parts[0]}.{parts[1]}"
    return parts[0]


def _declared(section: str) -> set[str]:
    """Import names this package declares in ``pyproject.toml``.

    Args:
        section: ``dependencies`` for the runtime set, or the name of an entry
            under ``optional-dependencies``.
    """
    config = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    raw = (
        project["dependencies"]
        if section == "dependencies"
        else project["optional-dependencies"][section]
    )
    names = set()
    for requirement in raw:
        # "anthropic>=0.40.0" -> "anthropic". Crude, and sufficient: these are
        # hand-written names, not arbitrary PEP 508 with markers and extras.
        distribution = requirement.split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip()
        names.add(DISTRIBUTION_TO_IMPORT.get(distribution, distribution.replace("-", "_")))
    return names


def _imported_roots(directory: pathlib.Path) -> dict[str, set[str]]:
    """Map each imported module key to the files importing it.

    ``ast.walk`` rather than a scan of module-level statements, so an import
    hidden inside a function is caught too. Those are the ones worth catching:
    a deferred import is exactly how a forbidden dependency gets in without
    looking like one.
    """
    found: dict[str, set[str]] = {}
    for path in sorted(directory.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [_import_key(alias.name) for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # `level > 0` is a relative import, which cannot leave the
                # package by construction.
                roots = [_import_key(node.module)] if node.module and node.level == 0 else []
            else:
                continue
            for root in roots:
                found.setdefault(root, set()).add(str(path.relative_to(PACKAGE_ROOT)))
    return found


COMPOSITION_ROOT = "interfaces"
"""The one layer allowed to read configuration. See `interfaces/__init__.py`."""

ENVIRONMENT_READERS = frozenset({"getenv", "environ"})
"""Names on `os` that reach the process environment."""

DOTENV = "dotenv"
"""Loading a `.env` file is a configuration read too, and an easier one to miss."""


def _configuration_read(node: ast.AST) -> str | None:
    """Name the configuration read this node performs, if it performs one.

    Four spellings of the same mistake: ``os.getenv``, ``os.environ``, the same
    two borrowed with ``from os import``, and any use of ``dotenv``. Matching on
    the attribute rather than resolving names means ``os`` rebound to something
    else would be missed -- accepted, because this guards against the ordinary
    version of the mistake, not a determined one.
    """
    if isinstance(node, ast.Attribute) and node.attr in ENVIRONMENT_READERS:
        if isinstance(node.value, ast.Name) and node.value.id == "os":
            return f"os.{node.attr}"
        return None
    if isinstance(node, ast.ImportFrom):
        if node.module == "os":
            borrowed = sorted(a.name for a in node.names if a.name in ENVIRONMENT_READERS)
            return ", ".join(f"os.{name}" for name in borrowed) or None
        return DOTENV if node.module and node.module.split(".")[0] == DOTENV else None
    if isinstance(node, ast.Import):
        return DOTENV if any(a.name.split(".")[0] == DOTENV for a in node.names) else None
    return None


def _configuration_reads_below_the_composition_root() -> dict[str, set[str]]:
    """Map each configuration read outside `interfaces/` to the files doing it."""
    found: dict[str, set[str]] = {}
    for path in sorted(SOURCE.rglob("*.py")):
        if COMPOSITION_ROOT in path.relative_to(SOURCE).parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            read = _configuration_read(node)
            if read is not None:
                found.setdefault(read, set()).add(str(path.relative_to(PACKAGE_ROOT)))
    return found


def test_only_the_composition_root_reads_configuration():
    """Nothing below `interfaces/` learns anything from the environment.

    The property that lets a host compose this agent at all. `bacteria.app`
    builds its clients from its own `Settings`, so a module below the
    composition root reading `MODEL_PROVIDER` for itself would ignore the
    host's configuration entirely -- and do it silently, since the variable is
    usually also set in development. The same read at import time freezes the
    value for the process, which is how a test that patches the environment ends
    up calling a live vendor API.

    Static, and for the reason the module docstring gives: an environment read
    below this line does not fail here, where `.env` is loaded and every variable
    is present. It fails in the host.
    """
    offenders = _configuration_reads_below_the_composition_root()

    assert offenders == {}, (
        f"only `{COMPOSITION_ROOT}/` may read configuration; these modules read it directly.\n"
        "Take the value as an argument instead -- the composition root is what knows it.\n"
        f"{offenders}"
    )


def test_the_source_imports_only_what_this_package_declares():
    """Nothing enters `bacteria.agent` that its own metadata does not promise.

    Catches two failures with one assertion. A sibling package from whatever
    workspace this happens to sit in — the one that would make the agent
    unvendorable — and an undeclared third-party import, which works on the
    machine that added it and fails on a clean install.
    """
    allowed = set(sys.stdlib_module_names) | {SELF} | _declared("dependencies")

    offenders = {
        root: sorted(files)
        for root, files in _imported_roots(SOURCE).items()
        if root not in allowed
    }

    assert offenders == {}, (
        "bacteria/agent/src imports modules it does not declare in pyproject.toml.\n"
        "Either declare the dependency, or -- if it belongs to the host -- "
        "invert it behind a protocol the host implements.\n"
        f"{offenders}"
    )


def test_the_tests_import_only_what_this_package_declares():
    """The suite ships with the package, so it is bound by the same rule.

    Worth asserting separately: borrowing a fixture or a helper from the
    application is a much easier mistake to make than importing it from
    `src/`, and it breaks vendoring just as completely — the tests are what a
    new host runs first to check the agent still works.
    """
    allowed = set(sys.stdlib_module_names) | {SELF} | _declared("dependencies") | _declared("dev")

    offenders = {
        root: sorted(files) for root, files in _imported_roots(TESTS).items() if root not in allowed
    }

    assert offenders == {}, (
        f"bacteria/agent tests import modules the package does not declare.\n{offenders}"
    )
