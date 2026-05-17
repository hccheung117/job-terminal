from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from job_terminal_models import Decision, Job  # noqa: F401  (register tables)
from models import Criteria, Stopword, User  # noqa: F401  (register tables)


@pytest.fixture()
def engine() -> Engine:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture()
def now() -> datetime:
    return datetime(2026, 5, 17, tzinfo=timezone.utc)


def make_user(session: Session, name: str = "Alice", email: str | None = None) -> User:
    user = User(id=uuid4(), name=name, email=email or f"{name.lower()}@example.com")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.expunge(user)
    return user


def make_job(
    session: Session,
    source_id: str,
    title: str,
    *,
    source_name: str = "linkedin",
    groups: list[str] | None = None,
) -> Job:
    job = Job(
        source_name=source_name,
        source_id=source_id,
        title=title,
        groups=groups or [],
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    session.expunge(job)
    return job


def add_decision(
    session: Session,
    user_id: UUID,
    job: Job,
    step: str,
    score: int,
    reason: str | None = None,
) -> None:
    session.add(
        Decision(
            user_id=user_id,
            source_name=job.source_name,
            source_id=job.source_id,
            step=step,
            score=score,
            reason=reason,
            judged_at=datetime(2026, 5, 17, tzinfo=timezone.utc),
        )
    )
    session.commit()
