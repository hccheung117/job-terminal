from sqlmodel import Session, select

from conftest import add_decision, make_job, make_user
from job_terminal_models import Decision
from models import Criteria
from steps.judge_title import (
    STEP,
    JudgeTitlePlan,
    TitleVerdict,
    execute_judge_title_plan,
    plan_judge_title,
)


def _seed(session: Session):
    user = make_user(session)
    job_pass = make_job(session, "1", "Senior Python Engineer")
    job_other = make_job(session, "2", "Frontend Designer")
    session.add(Criteria(user_id=user.id, criteria="I want Python backend roles."))
    session.commit()
    return user, job_pass, job_other


def test_plan_only_includes_title_filter_passes(engine):
    with Session(engine) as session:
        user, job_pass, job_other = _seed(session)
        add_decision(session, user.id, job_pass, "title_filter", score=1)
        add_decision(session, user.id, job_other, "title_filter", score=0, reason="stopword: frontend")

    plans = plan_judge_title(engine)
    assert [(p.user_id, p.source_id, p.title) for p in plans] == [
        (user.id, "1", "Senior Python Engineer"),
    ]


def test_plan_skips_already_judged(engine):
    with Session(engine) as session:
        user, job_pass, _ = _seed(session)
        add_decision(session, user.id, job_pass, "title_filter", score=1)
        add_decision(session, user.id, job_pass, STEP, score=1)

    assert plan_judge_title(engine) == []


def test_plan_requires_criteria_row(engine):
    with Session(engine) as session:
        user = make_user(session)
        job = make_job(session, "1", "Senior Python Engineer")
        add_decision(session, user.id, job, "title_filter", score=1)

    assert plan_judge_title(engine) == []


def test_execute_writes_decisions_via_injected_judge(engine):
    with Session(engine) as session:
        user, job_pass, _ = _seed(session)
        add_decision(session, user.id, job_pass, "title_filter", score=1)

    plans = plan_judge_title(engine)

    def stub_judge(plan: JudgeTitlePlan) -> TitleVerdict:
        return TitleVerdict(passes=False, reason="not senior enough")

    written = execute_judge_title_plan(engine, plans, judge=stub_judge)
    assert written == 1

    with Session(engine) as session:
        rows = session.exec(select(Decision).where(Decision.step == STEP)).all()
        assert len(rows) == 1
        assert rows[0].score == 0
        assert rows[0].reason == "not senior enough"


def test_execute_pass_clears_reason(engine):
    with Session(engine) as session:
        user, job_pass, _ = _seed(session)
        add_decision(session, user.id, job_pass, "title_filter", score=1)

    plans = plan_judge_title(engine)

    def stub_judge(plan: JudgeTitlePlan) -> TitleVerdict:
        return TitleVerdict(passes=True, reason="looks like a fit")

    execute_judge_title_plan(engine, plans, judge=stub_judge)

    with Session(engine) as session:
        row = session.exec(select(Decision).where(Decision.step == STEP)).one()
        assert row.score == 1
        assert row.reason is None
