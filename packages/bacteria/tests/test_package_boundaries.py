"""What this package is allowed to import.

The rule these protect is the one that makes `bacteria` a library rather than a
layer: it depends on nothing from whatever hosts it, and on nothing it has not
declared. Break that and the agent stops being vendorable — which is the entire
premise of the layering.

Static analysis, not an import attempt, and that distinction is the reason this
file exists. In the workspace this package currently lives in, the application
is installed in the same virtualenv, so `import fastpaip` inside `bacteria/`
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
    """Map each top-level imported module to the files importing it.

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
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # `level > 0` is a relative import, which cannot leave the
                # package by construction.
                roots = [node.module.split(".")[0]] if node.module and node.level == 0 else []
            else:
                continue
            for root in roots:
                found.setdefault(root, set()).add(str(path.relative_to(PACKAGE_ROOT)))
    return found


def test_the_source_imports_only_what_this_package_declares():
    """Nothing enters `bacteria` that its own metadata does not promise.

    Catches two failures with one assertion. A sibling package from whatever
    workspace this happens to sit in — the one that would make the agent
    unvendorable — and an undeclared third-party import, which works on the
    machine that added it and fails on a clean install.
    """
    allowed = set(sys.stdlib_module_names) | {"bacteria"} | _declared("dependencies")

    offenders = {
        root: sorted(files)
        for root, files in _imported_roots(SOURCE).items()
        if root not in allowed
    }

    assert offenders == {}, (
        "bacteria/src imports modules it does not declare in pyproject.toml.\n"
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
    allowed = (
        set(sys.stdlib_module_names) | {"bacteria"} | _declared("dependencies") | _declared("dev")
    )

    offenders = {
        root: sorted(files) for root, files in _imported_roots(TESTS).items() if root not in allowed
    }

    assert offenders == {}, (
        f"bacteria/tests imports modules the package does not declare.\n{offenders}"
    )
