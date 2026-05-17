from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKeyConstraint
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    email: str = Field(unique=True)


class Decision(SQLModel, table=True):
    __tablename__ = "decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_name", "source_id"],
            ["jobs.source_name", "jobs.source_id"],
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
    )
    user_id: UUID = Field(primary_key=True)
    source_name: str = Field(primary_key=True)
    source_id: str = Field(primary_key=True)
    step: str = Field(primary_key=True)
    score: int
    reason: str | None = None
    judged_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


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
