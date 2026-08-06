from typing import Optional
from sqlmodel import SQLModel, Field, Session, create_engine, select

UserId = int


class UserCreate(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    email: str


class User(UserCreate, table=True):
    id: Optional[UserId] = Field(default=None, primary_key=True)
