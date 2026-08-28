"""Reading and writing the project list.

Ownership is filtered here rather than checked afterwards. A query that returns
another principal's project and is then discarded by a caller has already
decided the wrong thing once, and the second caller to forget the check is the
one that ships.
"""

from typing import Optional

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.architecture.models import ArchitectureProject, Project


def _project(row: ArchitectureProject) -> Project:
    return Project(
        project_id=row.project_id,
        principal_id=row.principal_id,
        name=row.name,
        location=row.location,
        added_at=row.added_at,
    )


class SqlProjectRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, project: ArchitectureProject) -> Project:
        self._db.add(project)
        await self._db.flush()
        return _project(project)

    async def owned_by(self, principal_id: str) -> list[Project]:
        rows = await self._db.exec(
            select(ArchitectureProject)
            .where(col(ArchitectureProject.principal_id) == principal_id)
            .order_by(col(ArchitectureProject.added_at))
        )
        return [_project(row) for row in rows.all()]

    async def owned(self, principal_id: str, project_id: str) -> Optional[Project]:
        """One project, or ``None`` when it is missing **or somebody else's**.

        The two cases are deliberately indistinguishable to a caller. Answering
        "that exists but is not yours" tells an unauthenticated guesser which
        ids are real, and no caller here has a reason to tell them apart.
        """
        rows = await self._db.exec(
            select(ArchitectureProject).where(
                col(ArchitectureProject.principal_id) == principal_id,
                col(ArchitectureProject.project_id) == project_id,
            )
        )
        row = rows.first()
        return _project(row) if row is not None else None

    async def named(self, principal_id: str, location: str) -> Optional[Project]:
        rows = await self._db.exec(
            select(ArchitectureProject).where(
                col(ArchitectureProject.principal_id) == principal_id,
                col(ArchitectureProject.location) == location,
            )
        )
        row = rows.first()
        return _project(row) if row is not None else None
