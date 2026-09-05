"""HTTP surface for codebases and their architecture.

Ownership is decided here, beside the resource, per ADR 0004 -- ``auth``
answered who is calling and has no opinion about whose project this is.

The model is returned whole rather than paged. It is a few hundred kilobytes for
a large repository, the client needs all of it to lay out a scene, and a paged
graph is a graph the client has to reassemble before it can draw anything.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from bacteria.app.architecture.catalogue import ABOVE, IS_A, SAME_AS
from bacteria.app.architecture.checks import Boundary, Crossing
from bacteria.app.architecture.classify import sentence
from bacteria.app.architecture.conversation import ask
from bacteria.app.architecture.decisions import (
    NotALayer,
    NothingToRename,
    Verdict,
    decide,
    decisions,
    ontology_of,
    order,
    rename,
    sits_above,
    stranded,
)
from bacteria.app.architecture.models import Project
from bacteria.app.architecture.probes import Reading, run_tests
from bacteria.app.architecture.repository import SqlProjectRepository
from bacteria.app.architecture.service import UnusableLocation, add_project, model_of
from bacteria.app.auth.dependencies import CurrentPrincipal
from bacteria.app.core.dependencies import DbSession
from bacteria.app.core.model_client import build_model_client
from bacteria.app.core.settings import get_settings
from bacteria.app.graph.repository import SqlGraphRepository

router = APIRouter(prefix="/architecture", tags=["architecture"])


class Question(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class AnswerOut(BaseModel):
    """What the model said, and what it looked at to say it.

    ``tools_used`` is sent because an answer grounded in the parse and one
    invented from a plausible package name read identically to a person. An
    empty list is the signal to distrust the reply, and hiding it would remove
    the only way to tell.
    """

    reply: str
    tools_used: list[str]
    refused: list[str]
    """Capabilities the model asked for and the gate would not allow.

    Normally empty. Non-empty means a model reached for something this surface
    does not offer, which is worth seeing rather than swallowing — it is the
    gate doing its job out loud, the way ``chat/service.py`` argues an
    auto-approver should.
    """


class NewProject(BaseModel):
    location: str = Field(min_length=1)
    name: str = ""
    test_command: str = ""
    """What to run to check this project, set once when it is configured.

    Accepted here and nowhere else. The probe that runs it never takes a command
    from a request — a route that did would be remote code execution with extra
    steps, whatever the intent of whoever added it.
    """


class ProjectOut(BaseModel):
    project_id: str
    name: str
    location: str
    test_command: Optional[str] = None
    added_at: datetime


class ReadingOut(BaseModel):
    """What the world said when we asked, and when.

    Deliberately not shaped like an assertion. It has no validity interval and
    no author because nobody said it — a process exited with a status, which is
    a different kind of thing from a claim, and giving it a claim's shape would
    invite it into a log it must never enter.
    """

    probe: str
    state: str
    """``ok``, ``failing`` or ``unavailable``.

    Three and not two: a project that never said how to test itself has not been
    checked, which is not the same as having been checked and found fine. A
    surface drawing them alike reports a green tick for a suite nobody ran.
    """

    detail: str
    output: str
    at: datetime


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
    rel: str
    """Which relation the finding is about.

    Sent because not every crossing is an import: a table declared in the wrong
    package breaks a boundary too, and a client rendering every finding as
    ``<src> imports <dst>`` would describe it wrongly. The field used to be
    absent because every finding was forced into an import's shape.
    """

    dst: str
    line: int
    """``0`` where the offence is a declaration rather than a line of code."""


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

    verdict: Optional[str] = None
    """``agreed``, ``disagreed``, or absent while nobody has said.

    Three states rather than a boolean, because *not yet judged* and *judged no*
    are the two a review surface must never conflate — and the second is the one
    worth measuring.
    """

    stated_by: Optional[str] = None


class Judgment(BaseModel):
    subject: str
    claim: str
    verdict: Verdict


class Rename(BaseModel):
    """A statement that a package this codebase had is one it still has."""

    was: str
    now_called: str


class Order(BaseModel):
    """A statement that one layer sits above another."""

    upper: str
    lower: str


class OrphanOut(BaseModel):
    """A judgment about something the parse no longer produces.

    Reported rather than dropped. A decision whose subject has gone keeps
    standing in the log and joins to no proposal, so before this it disappeared
    from every surface while remaining true — which is the worst of both, since
    nobody can act on a record they cannot see.

    Whether it is an orphan or a rename is not decidable from the tree: a
    package that vanished and a package that changed name look identical to a
    parse. So it is shown and a person says which.
    """

    subject: str
    claim: str
    verdict: str
    stated_by: Optional[str] = None
    relation: str = IS_A
    """Which relation was stranded, because two now can be.

    Defaulted so the field is additive on the wire. A judgment strands when its
    subject leaves the tree; an ordering strands when one of its ends stops
    being agreed a layer, and a client that cannot tell them apart would offer
    the wrong repair for one of the two.
    """


class ModelOut(BaseModel):
    project: ProjectOut
    roots: list[str]
    modules: list[ModuleOut]
    imports: list[ImportOut]
    tables: list[str]
    boundaries: list[BoundaryOut]
    crossings: list[CrossingOut]
    proposals: list[ClassificationOut]
    order: list[str]
    """The stated layer order, floor first.

    Empty until somebody says one, and that emptiness is the honest state rather
    than a gap: the console falls back to ranking by imports, which is free and
    wrong in a way only a person can correct.
    """
    orphans: list[OrphanOut]
    """Judgments about subjects this codebase no longer has.

    Empty in the ordinary case. Non-empty after somebody renames or deletes a
    package, and the number is the one thing the model can say without
    guessing which of the two happened.
    """


def _project_out(project: Project) -> ProjectOut:
    return ProjectOut(
        project_id=project.project_id,
        name=project.name,
        location=project.location,
        test_command=project.test_command,
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
            test_command=body.test_command,
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

    # A proposal already judged still appears, carrying its verdict. Hiding
    # what somebody rejected would make the surface unable to show that anything
    # was ever rejected, which is the one number it exists to produce.
    graph = SqlGraphRepository(db, ontology=ontology_of(project))
    standing = await decisions(graph, project=project)
    judged = {(d.subject, d.claim): (d.verdict, d.stated_by) for d in standing}

    # A judgment lands nowhere when the parse stopped producing its subject.
    # Computed against the proposals rather than the package list, because a
    # judgment about a *word* -- `service is a role` -- is orphaned when the word
    # stops recurring, not when a package disappears.
    proposed = {(p.subject, p.claim) for p in model.proposals}
    orphans = [
        OrphanOut(subject=d.subject, claim=d.claim, verdict=d.verdict, stated_by=d.stated_by)
        for d in standing
        if (d.subject, d.claim) not in proposed
    ]
    # An ordering strands on a different condition -- one end stopped being
    # agreed a layer, rather than a subject leaving the tree -- so it is asked
    # for separately and joins the same list, which is what a person reads.
    orphans += [
        OrphanOut(
            subject=d.subject,
            claim=d.claim,
            verdict=d.verdict,
            stated_by=d.stated_by,
            relation=ABOVE,
        )
        for d in await stranded(graph, project=project)
    ]

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
            CrossingOut(
                boundary=c.boundary.name,
                src=c.edge.src,
                rel=c.edge.rel,
                dst=c.edge.dst,
                line=c.edge.line,
            )
            for c in model.verdict.crossings
        ],
        order=list(await order(graph, project=project)),
        orphans=orphans,
        proposals=[
            ClassificationOut(
                subject=p.subject,
                relation=p.relation,
                claim=p.claim,
                sentence=sentence(p),
                because=p.because,
                verdict=judged.get((p.subject, p.claim), (None, None))[0],
                stated_by=judged.get((p.subject, p.claim), (None, None))[1],
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


@router.post("/projects/{project_id}/classifications", response_model=ClassificationOut)
async def judge_classification(
    project_id: str, body: Judgment, principal: CurrentPrincipal, db: DbSession
) -> ClassificationOut:
    """Agree or disagree with something the codebase suggested about itself.

    The only write on this surface, and the only place a person's opinion enters
    a model that is otherwise entirely read off the syntax. It is recorded with
    their name on it, which is what ``stated_by`` exists for.

    A claim the classifier no longer makes is refused rather than stored. The
    tree moves under these proposals, and a judgment about a regularity that has
    since gone is a decision about a codebase that no longer exists.
    """
    repository = SqlProjectRepository(db)
    project = await repository.owned(principal.id, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such project")

    model = model_of(project)
    matched = next(
        (p for p in model.proposals if p.subject == body.subject and p.claim == body.claim),
        None,
    )
    if matched is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="this codebase no longer suggests that",
        )

    graph = SqlGraphRepository(db, ontology=ontology_of(project))
    decision = await decide(
        graph,
        project=project,
        subject=body.subject,
        claim=body.claim,
        verdict=body.verdict,
        stated_by=principal.id,
        now=datetime.now(timezone.utc),
    )
    await db.commit()

    return ClassificationOut(
        subject=matched.subject,
        relation=matched.relation,
        claim=matched.claim,
        sentence=sentence(matched),
        because=matched.because,
        verdict=decision.verdict,
        stated_by=decision.stated_by,
    )


def _reading_out(reading: Reading) -> ReadingOut:
    return ReadingOut(
        probe=reading.probe,
        state=reading.state,
        detail=reading.detail,
        output=reading.output,
        at=reading.at,
    )


@router.post("/projects/{project_id}/probes/tests", response_model=ReadingOut)
async def probe_tests(project_id: str, principal: CurrentPrincipal, db: DbSession) -> ReadingOut:
    """Run the project's own test command and report what happened.

    **A world-action**, and the first thing in this feature that is not a read.
    It changes nothing in the model: the answer is returned, shown and
    forgotten, because the tests were green four minutes ago and may be red now.
    A fact with a shelf life of one commit has no business in a log built to
    reconstruct what was believed last March.

    Takes no body. The command is the project's, set when it was configured, and
    a caller says *take the reading* rather than *run this*.
    """
    repository = SqlProjectRepository(db)
    project = await repository.owned(principal.id, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such project")

    return _reading_out(await run_tests(project))


@router.post("/projects/{project_id}/ask", response_model=AnswerOut)
async def ask_about(
    project_id: str, body: Question, principal: CurrentPrincipal, db: DbSession
) -> AnswerOut:
    """Ask a model about this codebase, with the codebase in front of it.

    The model is given three read-only tools and a gate that refuses everything
    else. It can recommend an action — agreeing with a proposal, accepting a
    crossing, running the suite — and cannot take one: over HTTP the approval
    gate has nobody to ask, since the request that would answer arrives after
    the one that asked.

    Stateless. Each ask re-derives the tree and discards the session, so an
    answer describes the working copy as it is rather than as it was when
    somebody last asked about it.
    """
    repository = SqlProjectRepository(db)
    project = await repository.owned(principal.id, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such project")

    model = model_of(project)
    # The verdicts are the reader's, and the model must be told which proposals
    # they have ruled on -- otherwise it repeats an open guess back to them as
    # something they already agreed to.
    verdicts = {
        (d.subject, d.claim): d.verdict
        for d in await decisions(
            SqlGraphRepository(db, ontology=ontology_of(project)), project=project
        )
    }

    settings = get_settings()
    client = build_model_client(settings.model_provider)
    answer = await ask(client, model, body.text, verdicts)
    return AnswerOut(
        reply=answer.reply,
        tools_used=list(answer.tools_used),
        refused=list(answer.refused),
    )


@router.post("/projects/{project_id}/renames", response_model=ClassificationOut)
async def rename_package(
    project_id: str, body: Rename, principal: CurrentPrincipal, db: DbSession
) -> ClassificationOut:
    """Say that a package the parse no longer finds is one it does, renamed.

    The judgments recorded under the old name then report under the new one,
    with their dates and authors intact. Nothing is rewritten: the rename is an
    assertion like every other statement on this surface, and retracting it puts
    the old judgments back where they were.

    **Both ends are checked against the tree**, and this is the only validation
    that matters. ``now_called`` must be something the parse currently produces
    or the judgments move to a subject nothing can display; ``was`` must be
    something it no longer produces, because a rename between two live packages
    is a claim that one codebase contains the same package twice.
    """
    repository = SqlProjectRepository(db)
    project = await repository.owned(principal.id, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such project")

    model = model_of(project)
    live = set(model.derived.packages)
    if body.now_called not in live:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"this codebase has no package called {body.now_called}",
        )
    if body.was in live:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"{body.was} is still here, so it was not renamed",
        )

    graph = SqlGraphRepository(db, ontology=ontology_of(project))
    try:
        stated = await rename(
            graph,
            project=project,
            was=body.was,
            now_called=body.now_called,
            stated_by=principal.id,
            now=datetime.now(timezone.utc),
        )
    except NothingToRename as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()

    return ClassificationOut(
        subject=stated.subject,
        relation=SAME_AS,
        claim=stated.claim,
        sentence=f"{stated.subject} is {stated.claim} under a new name",
        because="stated by a person",
        verdict=stated.verdict,
        stated_by=stated.stated_by,
    )


@router.post("/projects/{project_id}/order", response_model=ClassificationOut)
async def state_order(
    project_id: str, body: Order, principal: CurrentPrincipal, db: DbSession
) -> ClassificationOut:
    """Say that one layer sits above another.

    **The only axis this model has, and nothing derives it.** Ranking packages
    by longest path through their imports is free and repeatable, and on a
    codebase with two import cycles it puts most of the tree in three adjacent
    bands -- so a person states the order and the imports are then read
    *against* it.

    Both ends must already be agreed layers. That is checked against the log
    rather than the tree, which makes this the first route whose validity rests
    on another judgment; classify the packages first and the refusal says so.
    """
    repository = SqlProjectRepository(db)
    project = await repository.owned(principal.id, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such project")

    graph = SqlGraphRepository(db, ontology=ontology_of(project))
    try:
        stated = await sits_above(
            graph,
            project=project,
            upper=body.upper,
            lower=body.lower,
            stated_by=principal.id,
            now=datetime.now(timezone.utc),
        )
    except NotALayer as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()

    return ClassificationOut(
        subject=stated.subject,
        relation=ABOVE,
        claim=stated.claim,
        sentence=f"{stated.subject} sits above {stated.claim}",
        because="stated by a person",
        verdict=stated.verdict,
        stated_by=stated.stated_by,
    )
