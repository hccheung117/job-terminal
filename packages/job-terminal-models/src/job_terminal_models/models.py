from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, ForeignKeyConstraint, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    source_name: str = Field(primary_key=True)
    source_id: str = Field(primary_key=True)
    groups: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    location: str | None = None
    title: str | None = None
    jd: str | None = None
    url: str | None = None
    title_clean: str | None = None
    reqs_hard: str | None = None
    reqs_soft: str | None = None
    role: str | None = None
    unlisted: int = 0
    published_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    first_seen_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


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
