from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    email: str = Field(unique=True)


class Stopword(SQLModel, table=True):
    __tablename__ = "stopwords"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('group', 'user')",
            name="stopwords_scope_type_check",
        ),
    )

    scope_type: str = Field(primary_key=True)
    scope_id: str = Field(primary_key=True)
    keyword: str = Field(primary_key=True)
