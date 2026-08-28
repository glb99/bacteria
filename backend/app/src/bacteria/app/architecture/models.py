"""The codebases this deployment has been pointed at.

The only table this feature owns, and it holds **nothing derived**. A project is
a stated fact -- somebody added this repository -- and the modules, imports and
tables inside it are re-read from disk on demand. Storing the parse would make
this a cache pretending to be a record, and the first time the two disagreed the
row would win against the file, which is the wrong way round.

So the row answers *which codebases are we watching* and nothing else.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tz_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False)


def new_project_id() -> str:
    return uuid.uuid4().hex


class ArchitectureProject(SQLModel, table=True):
    """One codebase, by the path it lives at.

    ``principal_id`` is the owner, and it is here rather than implied because a
    project is the first thing in this system stated *into a shared scope*: the
    architecture of a repository belongs to whoever is working on it, and a team
    reading the same model needs to know who added it. It is also the smallest
    version of the author field the graph does not yet have.

    ``location`` is an absolute path on the machine running the service, which
    is a real exposure and is bounded deliberately: the service reads ``*.py``
    under it and nothing else, writes nothing, and executes nothing. A
    deployment that should not permit arbitrary paths restricts them in
    :func:`bacteria.app.architecture.service.add_project`, which is the one
    place that resolves them.

    Not built:
        Cloning from a git URL. It needs a workspace directory, a subprocess and
        a decision about which remotes are permitted, and none of that is needed
        to read a checkout that is already on the machine. ``location`` is a
        path today and would gain a sibling column rather than change meaning.
    """

    __tablename__ = "architecture_project"

    project_id: str = Field(default_factory=new_project_id, primary_key=True)
    principal_id: str = Field(index=True)
    name: str
    location: str
    added_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())


@dataclass(frozen=True)
class Project:
    """A project as a reader sees it, detached from the session that loaded it.

    The table row is never handed out. SQLAlchemy expires an instance's
    attributes on commit, so a route that commits and *then* reads one triggers
    a lazy refresh outside the greenlet the async driver runs in -- which fails
    as ``MissingGreenlet``, at the point of rendering rather than at the point
    of the mistake. This package learned that by doing it.

    The graph package reached the same shape for the same reason; see
    ``bacteria.app.graph.repository``.
    """

    project_id: str
    principal_id: str
    name: str
    location: str
    added_at: datetime
