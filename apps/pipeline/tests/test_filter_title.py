from sqlmodel import Session, select

from conftest import make_job, make_user
from job_terminal_models import Decision
from models import Stopword
from steps.filter_title import (
    STEP,
    execute_filter_title_plan,
    plan_filter_title,
)


def test_filter_writes_pass_and_reject_rows(engine):
    with Session(engine) as session:
        user = make_user(session)
        user_id = user.id
        make_job(session, "1", "Senior Python Engineer", groups=["backend"])
        make_job(session, "2", "Java Developer", groups=["backend"])
        session.add(Stopword(scope_type="group", scope_id="backend", keyword="java"))
        session.commit()

    plans = plan_filter_title(engine)
    assert {(p.source_id, p.score) for p in plans} == {("1", 1), ("2", 0)}

    written = execute_filter_title_plan(engine, plans)
    assert written == 2

    with Session(engine) as session:
        rows = session.exec(
            select(Decision).where(Decision.step == STEP).order_by(Decision.source_id)
        ).all()
        assert [(r.source_id, r.score, r.reason) for r in rows] == [
            ("1", 1, None),
            ("2", 0, "stopword: java"),
        ]
        assert all(r.user_id == user_id for r in rows)


def test_filter_skips_already_decided(engine):
    from conftest import add_decision

    with Session(engine) as session:
        user = make_user(session)
        job = make_job(session, "1", "Senior Python Engineer", groups=["backend"])
        add_decision(session, user.id, job, STEP, score=1)

    assert plan_filter_title(engine) == []
