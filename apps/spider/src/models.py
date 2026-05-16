from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel


class SpiderKeyword(SQLModel, table=True):
    __tablename__ = "spider_keywords"

    id: int | None = Field(default=None, primary_key=True)
    group: str = Field(index=True)
    keyword: str


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
    published_at: str | None = None
    first_seen_at: str | None = None
