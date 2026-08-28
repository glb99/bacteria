"""HTTP surface for codebases and their architecture.

Ownership is decided here, beside the resource, per ADR 0004 -- ``auth``
answered who is calling and has no opinion about whose project this is.

The model is returned whole rather than paged. It is a few hundred kilobytes for
a large repository, the client needs all of it to lay out a scene, and a paged
graph is a graph the client has to reassemble before it can draw anything.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from bacteria.app.architecture.checks import Boundary, Crossing
from bacteria.app.architecture.classify import sentence
from bacteria.app.architecture.models import Project
from bacteria.app.architecture.repository import SqlProjectRepository
from bacteria.app.architecture.service import UnusableLocation, add_project, model_of
from bacteria.app.auth.dependencies import CurrentPrincipal
from bacteria.app.core.dependencies import DbSession

router = APIRouter(prefix="/architecture", tags=["architecture"])


class NewProject(BaseModel):
    location: str = Field(min_length=1)
    name: str = ""


class ProjectOut(BaseModel):
    project_id: str
    name: str
    location: str
    added_at: datetime


class ModuleOut(BaseModel):
    name: str
    path: str
    package: str
    tables: list[str]


class ImportOut(BaseModel):
    src: str
    dst: str
    deferred: bool
    """Whether the import runs on call rather than on load.

    Sent because it is the difference between a deliberate deferral and an
    eroded layer, and a client that cannot draw them differently would report
    six violations on this codebase that its own boundary does not have.
    """

    line: int


class BoundaryOut(BaseModel):
    name: str
    sentence: str
    state: str
    """One of ``holds``, ``crossed``, ``undecidable`` or ``inapplicable``.

    ``undecidable`` is a state and not an omission: four of this codebase's
    eight boundaries are about what a module contains, which no import can
    settle, and a client that showed only the other four would imply it had
    checked everything. ``inapplicable`` is the same problem from the other
    side: a rule about packages this repository does not contain passes by
    describing nothing, and must not be drawn as a rule that was satisfied.
    """

    elsewhere: Optional[str] = None


class CrossingOut(BaseModel):
    boundary: str
    src: str
    dst: str
    line: int


class ClassificationOut(BaseModel):
    """One claim about this codebase that a person may accept or reject.

    The only uncertain thing this feature produces. An import is exact and not
    worth arguing about; *"chat is a feature"* is a judgment drawn from a
    regularity, and the surface has to draw the two differently or the second
    gets trusted like the first.

    ``because`` travels because a proposal nobody can check is one they will
    approve without checking, which is the review-fatigue failure rather than a
    convenience.
    """

    subject: str
    relation: str
    claim: str
    sentence: str
    because: str


class ModelOut(BaseModel):
    project: ProjectOut
    roots: list[str]
    modules: list[ModuleOut]
    imports: list[ImportOut]
    tables: list[str]
    boundaries: list[BoundaryOut]
    crossings: list[CrossingOut]
    proposals: list[ClassificationOut]


def _project_out(project: Project) -> ProjectOut:
    return ProjectOut(
        project_id=project.project_id,
        name=project.name,
        location=project.location,
        added_at=project.added_at,
    )


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: NewProject, principal: CurrentPrincipal, db: DbSession
) -> ProjectOut:
    """Point the service at a checkout.

    Adding the same location twice returns the existing project rather than
    failing. It is the same statement made again, and a duplicate-key error for
    "I already told you that" is a worse answer than the row.
    """
    repository = SqlProjectRepository(db)
    try:
        project = await add_project(
            repository,
            principal_id=principal.id,
            name=body.name,
            location=body.location,
            permitted=_permitted_roots(),
        )
    except UnusableLocation as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.reason) from exc
    await db.commit()
    return _project_out(project)


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(principal: CurrentPrincipal, db: DbSession) -> list[ProjectOut]:
    repository = SqlProjectRepository(db)
    return [_project_out(p) for p in await repository.owned_by(principal.id)]


@router.get("/projects/{project_id}/model", response_model=ModelOut)
async def read_model(project_id: str, principal: CurrentPrincipal, db: DbSession) -> ModelOut:
    """The codebase as it stands on disk right now, judged against its rules.

    Re-read on every request. The alternative is a stored copy that disagrees
    with the working tree exactly when somebody is editing it, which is the only
    time anybody looks.
    """
    repository = SqlProjectRepository(db)
    project = await repository.owned(principal.id, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such project")

    try:
        model = model_of(project)
    except OSError as exc:
        # The checkout moved or was deleted since it was added. A 409 rather
        # than a 500: nothing is broken, the world changed under a stored path.
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"cannot read {project.location}"
        ) from exc

    # Crossed first: the list is read top-down and the thing to act on belongs
    # where a reader starts, not after everything that is fine.
    boundaries = [_boundary_out(b, "crossed") for b in _crossed_boundaries(model.verdict.crossings)]
    boundaries += [_boundary_out(b, "holds") for b in model.verdict.held]
    boundaries += [_boundary_out(b, "undecidable") for b in model.verdict.undecidable]
    boundaries += [_boundary_out(b, "inapplicable") for b in model.verdict.inapplicable]

    return ModelOut(
        project=_project_out(project),
        roots=list(model.roots),
        modules=[
            ModuleOut(name=m.name, path=m.path, package=m.package, tables=list(m.tables))
            for m in model.derived.modules.values()
        ],
        imports=[
            ImportOut(src=i.src, dst=i.dst, deferred=i.deferred, line=i.line)
            for i in model.derived.imports
        ],
        tables=list(model.derived.tables),
        boundaries=boundaries,
        crossings=[
            CrossingOut(boundary=c.boundary.name, src=c.edge.src, dst=c.edge.dst, line=c.edge.line)
            for c in model.verdict.crossings
        ],
        proposals=[
            ClassificationOut(
                subject=p.subject,
                relation=p.relation,
                claim=p.claim,
                sentence=sentence(p),
                because=p.because,
            )
            for p in model.proposals
        ],
    )


def _boundary_out(boundary: Boundary, state: str) -> BoundaryOut:
    return BoundaryOut(
        name=boundary.name,
        sentence=boundary.sentence,
        state=state,
        elsewhere=boundary.elsewhere,
    )


def _crossed_boundaries(crossings: Sequence[Crossing]) -> list[Boundary]:
    """Each crossed boundary once, in the order it was first crossed.

    A verdict holds one crossing per offending edge, so a boundary broken six
    times appears six times; the boundary list wants it once and the six edges
    travel separately as crossings.
    """
    seen: dict[str, Boundary] = {}
    for crossing in crossings:
        seen.setdefault(crossing.boundary.name, crossing.boundary)
    return list(seen.values())


def _permitted_roots() -> tuple[Path, ...]:
    """Where projects may live.

    Empty, meaning anywhere on the machine, which is correct for the
    single-operator deployment this runs in and is the thing to change first for
    any other. It is a function rather than a constant so that tightening it is
    an edit here and not a search through the routes.
    """
    return ()
