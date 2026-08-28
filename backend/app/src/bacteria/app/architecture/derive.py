"""What the source says about itself, read from the syntax and nothing else.

The other ontology in this codebase is *testimony*: a model reads a transcript,
guesses what somebody meant, and writes a claim nobody can check. This one is
the opposite, and the difference decides the whole design. A module is its path,
so identity never has to be resolved. An import either exists or it does not, so
there is nothing to contradict. Re-running produces the same answer, so nothing
here needs to be stored to be trusted.

**Which is why nothing here is written to the assertion log.** The log exists
because testimony is unrepeatable — you cannot re-ask what somebody said last
March, so the row is the only record and must never be lost. A parse is
infinitely repeatable, and storing it would be a cache pretending to be a
memory. What *is* worth keeping is the small stated layer above this: the
boundaries somebody declared, the crossings they accepted, the rules they later
retired. See :mod:`~bacteria.app.architecture.checks`.

**The vocabulary is not ours and was not discovered.** ``module``, ``package``,
``import`` come from the language; ``table`` comes from SQLModel. The schema
growth doctrine that governs the relation catalogue -- propose on the third
sighting, ratify by hand -- is a rule about testimony, where you genuinely
cannot know in advance what will arrive. It does not apply to a domain whose
terms are fixed by a grammar somebody else already ratified.

Not built:
    Calls, classes, functions, routes and tests. All derivable from the same
    parse, and each answers questions nothing is asking yet. The cost of adding
    one later is a field; the cost of carrying five nobody reads is every
    reader wondering which matter.

    ``if TYPE_CHECKING:`` imports, which do not exist in this codebase and would
    need a third value for :attr:`Import.deferred` rather than a second.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Import:
    """One module naming another.

    ``deferred`` is the field that stops this being a toy. An import inside a
    function body is a different act from one at module level: it runs when the
    function is called rather than when the module is loaded, and it is the
    documented way out of a circular dependency. Treating the two as one edge
    reports a deliberate deferral as a layering violation, which is exactly what
    a coarser first pass over this codebase did -- six times, all of them from
    ``core/jobs.py`` registering task modules that procrastinate discovers by
    import.

    ``line`` travels because a crossing is only actionable if somebody can go
    and look at it.
    """

    src: str
    dst: str
    deferred: bool
    line: int


@dataclass(frozen=True)
class Module:
    """One source file, named the way Python names it.

    ``name`` is the dotted import path and is the identity. There is no
    resolution step and no possibility of two modules being the same thing,
    which is the single largest difference from the personal graph -- where
    deciding whether two mentions are one person is most of the difficulty.
    """

    name: str
    path: str
    package: str
    tables: tuple[str, ...]


@dataclass(frozen=True)
class Derived:
    """Everything the parse found, and nothing anybody said about it.

    Frozen and self-contained so that a check is a pure function of it. That is
    what lets the boundaries in :mod:`~bacteria.app.architecture.checks` be
    tested against hand-built inputs rather than against this repository, which
    would make every check a test of whatever the tree happened to look like on
    the day it was written.
    """

    modules: Mapping[str, Module]
    imports: tuple[Import, ...]

    @property
    def packages(self) -> tuple[str, ...]:
        return tuple(sorted({module.package for module in self.modules.values()}))

    @property
    def tables(self) -> tuple[str, ...]:
        return tuple(sorted({t for module in self.modules.values() for t in module.tables}))

    def within(self, prefix: str) -> tuple[str, ...]:
        """Module names under a dotted prefix, the prefix itself included.

        Boundaries are stated about regions -- *the agent*, *core*, *a feature*
        -- and a region is a prefix. Kept here rather than in each check so that
        ``bacteria.app.core`` never accidentally matches ``bacteria.app.corex``,
        which a bare ``startswith`` does.
        """
        return tuple(
            name for name in self.modules if name == prefix or name.startswith(f"{prefix}.")
        )


def derive(roots: Mapping[Path, str]) -> Derived:
    """Parse every module under each source root.

    ``roots`` maps a source directory to the label used in reporting, and is
    passed in rather than discovered because finding the roots is configuration
    and this is not an entrypoint. A workspace with two packages has two roots
    and their modules share one namespace, which is what makes an import from
    one to the other visible at all.

    A file that does not parse is skipped rather than raised on. This runs
    across a whole tree, and a single syntax error in a file nobody imports
    should not deny an answer about the other eighty-eight.
    """
    modules: dict[str, Module] = {}
    trees: dict[str, ast.Module] = {}

    for root, _label in roots.items():
        for path in sorted(root.rglob("*.py")):
            name = _dotted(path, root)
            package = name.rsplit(".", 1)[0] if "." in name else name
            tree = _parse(path)
            modules[name] = Module(
                name=name,
                path=path.as_posix(),
                package=package,
                tables=_tables(tree),
            )
            if tree is not None:
                trees[name] = tree

    # Resolution needs the whole set, so imports wait until every module is
    # known -- otherwise an edge to a file later in the walk resolves to
    # nothing and the answer depends on directory order.
    known = frozenset(modules)
    imports: list[Import] = []
    for name, tree in trees.items():
        imports.extend(_imports(tree, name, known))

    return Derived(modules=modules, imports=tuple(sorted(set(imports), key=_order)))


def _order(edge: Import) -> tuple[str, str, int]:
    return (edge.src, edge.dst, edge.line)


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return None


def _dotted(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _tables(tree: ast.Module | None) -> tuple[str, ...]:
    """Table names declared by a ``__tablename__`` literal in a class body.

    Only a literal. A computed table name would need the class evaluated, and a
    derivation that imports the code it is describing is a derivation that can
    be broken by the code it is describing.
    """
    if tree is None:
        return ()
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            names = (t.id for t in statement.targets if isinstance(t, ast.Name))
            if "__tablename__" in names and isinstance(statement.value, ast.Constant):
                found.add(str(statement.value.value))
    return tuple(sorted(found))


def _imports(tree: ast.Module, own: str, known: frozenset[str]) -> Iterable[Import]:
    for node, deferred in _statements(tree.body, deferred=False):
        for target in _targets(node, own):
            resolved = _resolve(target, known)
            if resolved and resolved != own:
                yield Import(src=own, dst=resolved, deferred=deferred, line=node.lineno)


def _statements(
    body: Sequence[ast.stmt], *, deferred: bool
) -> Iterable[tuple[ast.Import | ast.ImportFrom, bool]]:
    """Walk statements carrying whether we are inside a function body.

    A plain :func:`ast.walk` cannot answer this: it yields nodes without their
    parents, so an import three levels inside a method is indistinguishable from
    one at the top of the file. Descending explicitly is the only way to know,
    and knowing is the whole point of :attr:`Import.deferred`.
    """
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node, deferred
            continue
        inside = deferred or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for field in ("body", "orelse", "finalbody"):
            yield from _statements(getattr(node, field, []) or [], deferred=inside)
        for handler in getattr(node, "handlers", []) or []:
            yield from _statements(handler.body, deferred=inside)


def _targets(node: ast.Import | ast.ImportFrom, own: str) -> Iterable[str]:
    """Every dotted name an import statement could be naming.

    ``from x.y import z`` is ambiguous in the syntax -- ``z`` may be a module or
    a symbol -- so both readings are offered and :func:`_resolve` picks the one
    that names a module we actually found.
    """
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.name
        return

    if node.level:
        base = own.split(".")
        prefix = ".".join(base[: max(len(base) - node.level, 0)])
        target = f"{prefix}.{node.module}" if node.module else prefix
    else:
        target = node.module or ""

    if not target:
        return
    yield target
    for alias in node.names:
        yield f"{target}.{alias.name}"


def _resolve(target: str, known: frozenset[str]) -> str | None:
    """The module a dotted name refers to, or ``None`` for anything external.

    Longest match wins, and only two lengths are tried: the name itself, then
    its parent. ``from bacteria.app.graph.log import Assertion`` offers
    ``...log.Assertion`` first, which is not a module, and ``...log``, which is.
    """
    if target in known:
        return target
    parent = target.rsplit(".", 1)[0]
    return parent if parent in known else None
