"""Adding a codebase, and reading the model of one.

The two halves of this feature meet here and nowhere else: a project is a row,
its architecture is a parse, and **the parse is never stored**. Every read goes
back to the files, which is affordable because it is affordable -- 93 modules in
well under a second -- and honest, because a model of a codebase that disagrees
with the codebase is worse than no model.

Not built:
    Any cache. The obvious one is keyed on the head commit, and it would need
    invalidating on a dirty tree, which is the state a developer is in whenever
    they care. Measure a repository where this is slow before adding it; until
    then a cache is a second source of truth for a fact that is free.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from bacteria.app.architecture.checks import BOUNDARIES, Boundary, Verdict, evaluate
from bacteria.app.architecture.classify import Proposal, propose
from bacteria.app.architecture.derive import Derived, derive
from bacteria.app.architecture.layout import source_roots
from bacteria.app.architecture.models import ArchitectureProject, Project
from bacteria.app.architecture.repository import SqlProjectRepository


class UnusableLocation(Exception):
    """The path is not somewhere a codebase can be read from.

    A named failure rather than a bare ``ValueError`` because the caller has to
    tell it apart from a bug: a person typing a path wrong is the ordinary case
    and deserves an answer, not a five hundred.
    """

    def __init__(self, location: str, reason: str) -> None:
        super().__init__(f"{location}: {reason}")
        self.location = location
        self.reason = reason


@dataclass(frozen=True)
class Model:
    """A codebase as it stands right now, and how it measures against its rules.

    Carries the roots it was read from. A reader who sees ninety-three modules
    where they expected four hundred needs to know which directories were
    walked, and that question has been the first one worth asking every time
    this has been wrong.
    """

    project: Project
    roots: tuple[str, ...]
    derived: Derived
    verdict: Verdict
    proposals: tuple[Proposal, ...]


async def add_project(
    repository: SqlProjectRepository,
    *,
    principal_id: str,
    name: str,
    location: str,
    permitted: Sequence[Path] = (),
) -> Project:
    """Register a checkout, after checking it is one.

    Resolved before anything else, so that ``..`` and symlinks are settled once
    here rather than differently by each later reader.

    ``permitted`` bounds where projects may live and defaults to unbounded,
    which is the right default for the single-operator deployment this runs in
    and the wrong one for any other. It is a parameter rather than a setting
    because the entrypoint composing this is where deployment policy belongs --
    and it is the single place to tighten, which is why the resolution happens
    here and not in the route.
    """
    try:
        resolved = Path(location).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise UnusableLocation(location, "no such directory") from exc

    if not resolved.is_dir():
        raise UnusableLocation(location, "not a directory")

    if permitted and not any(_within(resolved, root) for root in permitted):
        raise UnusableLocation(location, "outside the permitted roots")

    if not source_roots(resolved):
        raise UnusableLocation(location, "no Python packages found under it")

    existing = await repository.named(principal_id, resolved.as_posix())
    if existing is not None:
        return existing

    return await repository.add(
        ArchitectureProject(
            principal_id=principal_id,
            name=name or resolved.name,
            location=resolved.as_posix(),
        )
    )


def _within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root.expanduser().resolve())
    except ValueError:
        return False
    return True


def model_of(project: Project, boundaries: Sequence[Boundary] = BOUNDARIES) -> Model:
    """Read the codebase and judge it.

    Synchronous, and the only part of this feature that touches a filesystem.
    Kept out of the repository and off the request path's database session so
    that a slow parse holds no connection -- the walk is the expensive thing
    here, and nothing about it wants a transaction.
    """
    base = Path(project.location)
    roots = source_roots(base)
    derived = derive(roots)
    return Model(
        project=project,
        roots=tuple(sorted(roots.values())),
        derived=derived,
        verdict=evaluate(derived, boundaries),
        # Recomputed with everything else rather than stored. A proposal is a
        # reading of the current tree; one kept from last week would be arguing
        # about a codebase that no longer exists.
        proposals=propose(derived),
    )
