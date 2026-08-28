"""Where the code is, for a repository nobody described to us.

``derive`` takes source roots and does not look for them, because parsing and
discovery fail differently: a bad parse loses one file, a bad root loses the
whole answer and looks like a small codebase rather than an error. Keeping them
apart means a caller who *knows* the layout can say so and skip this entirely.

**A root is found by climbing.** Every ``__init__.py`` marks a package; walk up
until the parent is not itself a package, and the parent of the outermost one is
a source root. That covers flat repositories and ``src/`` layouts without
knowing either shape by name.

**Then one convention, because climbing alone is wrong here.** A namespace
package (PEP 420) has no ``__init__.py``, so there is nothing to climb through
and the walk stops one level too low. This workspace is exactly that case:
``backend/app/src/bacteria`` holds only ``app`` and no ``__init__.py``, so
climbing yields ``.../src/bacteria`` as the root and every module loses its
``bacteria.`` prefix -- which silently drops **232 of 234 imports**, because
nothing resolves any more. It looked like a small tidy codebase rather than a
broken parse, which is the failure this module's first paragraph warns about,
found by running it.

So: if any ancestor of the outermost package is named ``src``, that directory is
the root. One convention, load-bearing, and stated rather than buried -- it is
the only name this module knows.
"""

from collections.abc import Iterable
from pathlib import Path

IGNORED = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "build",
        "dist",
        "site-packages",
        ".eggs",
    }
)
"""Directories never descended into.

``site-packages`` and ``.venv`` matter most: a virtualenv inside a checkout
holds thousands of modules that are not the project, and including them would
make every question about the codebase an answer about its dependencies.
"""

MAX_PACKAGES = 5000
"""A ceiling, so pointing this at a home directory fails fast rather than slowly."""


def source_roots(base: Path) -> dict[Path, str]:
    """The directories under ``base`` that Python would import packages from.

    Returns roots mapped to a short label -- the root's path relative to
    ``base`` -- which is what a reader needs to tell ``backend/app/src`` from
    ``backend/agent/src`` in a report.

    A root is never inside another root's package tree, because climbing stops
    at the outermost package. Two unrelated trees in one repository therefore
    give two roots, which is correct: their modules share one namespace only if
    the layout says so.
    """
    roots: dict[Path, str] = {}
    for package in _packages(base):
        outermost = package
        while (outermost.parent / "__init__.py").exists() and outermost.parent != base.parent:
            outermost = outermost.parent
        root = _src_ancestor(outermost, base) or outermost.parent
        if root not in roots:
            label = root.relative_to(base).as_posix() if root != base else "."
            roots[root] = label
    return roots


def _src_ancestor(package: Path, base: Path) -> Path | None:
    """The nearest ancestor named ``src``, if there is one inside ``base``.

    The namespace-package correction. Without it a package under
    ``src/<namespace>/`` reports ``src/<namespace>`` as the root, and every
    module is named without its namespace -- so imports that spell it in full
    resolve to nothing and the graph comes back nearly empty.
    """
    for ancestor in package.parents:
        if ancestor == base.parent:
            return None
        if ancestor.name == "src":
            return ancestor
    return None


def _packages(base: Path) -> Iterable[Path]:
    """Every directory under ``base`` holding an ``__init__.py``.

    Walked with an explicit stack rather than ``rglob`` so that an ignored
    directory is not descended into at all. ``rglob`` would visit every file in
    ``node_modules`` before discarding them, which on a real checkout is the
    difference between a moment and a minute.
    """
    seen = 0
    stack = [base]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            if not entry.is_dir() or entry.name in IGNORED or entry.name.startswith("."):
                continue
            if (entry / "__init__.py").exists():
                seen += 1
                if seen > MAX_PACKAGES:
                    return
                yield entry
            stack.append(entry)


def python_files(root: Path) -> list[Path]:
    """Every ``.py`` file under a source root, skipping what is not the project.

    Shared with :func:`bacteria.app.architecture.derive.derive` rather than left
    to a bare ``rglob``, which is what it used to do. The ignore list was
    applied when *finding* roots and not when *reading* them, so a repository
    with its virtualenv inside the root parsed the virtualenv: one checkout
    reported 1793 modules of which 1757 were installed dependencies, named
    things like ``.venv.Lib.site-packages._pytest``. It looked like a large
    codebase rather than a broken walk, and cost eight seconds a request to say
    nothing true.
    """
    found: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in IGNORED and not entry.name.startswith("."):
                    stack.append(entry)
            elif entry.suffix == ".py":
                found.append(entry)
    return sorted(found)
