from collections.abc import Generator
from typing import Annotated

from app.documents.document import DocumentRepository
from app.documents.entity_extractor import GeminiEntityExtractor, SendsForDetections
from app.documents.paginator import Paginate, paginate
from app.llm.embeddings import Embed, GeminiEmbedder
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.api.services.document_repository import SqlDocumentRepository
from app.core import security
from app.core.config import settings
from app.core.db import engine, scope_to_user
from app.core.file_system import LocalFileSystem
from app.models import TokenPayload, User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Generator[Session]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except InvalidTokenError, ValidationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_scoped_session(session: SessionDep, current_user: CurrentUser) -> Session:
    if not current_user.is_superuser:
        scope_to_user(session, str(current_user.id))
    return session


ScopedSessionDep = Annotated[Session, Depends(get_scoped_session)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user


def get_local_file_system() -> LocalFileSystem:
    return LocalFileSystem()


LocalFilesystemDep = Annotated[LocalFileSystem, Depends(get_local_file_system)]


def get_document_repository(scoped_sesion: ScopedSessionDep) -> DocumentRepository:
    return SqlDocumentRepository(scoped_sesion)


DocumentRepositoryDep = Annotated[
    DocumentRepository, Depends(get_document_repository)
]


def get_paginate() -> Paginate:
    return paginate


PaginateDep = Annotated[Paginate, Depends(get_paginate)]


def get_extract_entities() -> GeminiEntityExtractor:
    return GeminiEntityExtractor()


ExtractEntitiesDep = Annotated[GeminiEntityExtractor, Depends(
    get_extract_entities)]


def get_embedder() -> Embed:
    return GeminiEmbedder()


EmbedDep = Annotated[Embed, Depends(get_embedder)]


def get_model_client() -> SendsForDetections:
    return GeminiEntityExtractor()


ModelClientDep = Annotated[SendsForDetections, Depends(get_model_client)]
