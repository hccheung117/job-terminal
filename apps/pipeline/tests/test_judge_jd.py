from datetime import datetime, timezone

from sqlmodel import Session, select

from conftest import add_decision, make_job, make_user
from job_terminal_models import Decision
from models import Criteria
from steps.judge_jd import (
    STEP,
    JdVerdict,
    JudgeJdPlan,
    execute_judge_jd_plan,
    plan_judge_jd,
    plan_judge_jd_eval,
    render_judge_jd_plan,
)

TITLE_JUDGE = "title_judge"


def _seed(session: Session):
    user = make_user(session)
    job_pass = make_job(session, "1", "Senior Python Engineer", jd="Build Python services.")
    job_other = make_job(session, "2", "Staff Python Engineer", jd="Lead Python platform.")
    session.add(Criteria(user_id=user.id, criteria="I want Python backend roles."))
    session.commit()
    return user, job_pass, job_other


def test_plan_only_includes_title_judge_passes(engine):
    with Session(engine) as session:
        user, job_pass, job_other = _seed(session)
        add_decision(session, user.id, job_pass, TITLE_JUDGE, score=1)
        add_decision(session, user.id, job_other, TITLE_JUDGE, score=0, reason="too senior")

    plans = plan_judge_jd(engine)
    assert [(p.user_id, p.source_id, p.title, p.jd) for p in plans] == [
        (user.id, "1", "Senior Python Engineer", "Build Python services."),
    ]


def test_plan_skips_jobs_without_jd(engine):
    with Session(engine) as session:
        user = make_user(session)
        job = make_job(session, "1", "Senior Python Engineer", jd=None)
        session.add(Criteria(user_id=user.id, criteria="Python backend."))
        session.commit()
        add_decision(session, user.id, job, TITLE_JUDGE, score=1)

    assert plan_judge_jd(engine) == []


def test_plan_skips_already_judged(engine):
    with Session(engine) as session:
        user, job_pass, _ = _seed(session)
        add_decision(session, user.id, job_pass, TITLE_JUDGE, score=1)
        add_decision(session, user.id, job_pass, STEP, score=1)

    assert plan_judge_jd(engine) == []


def test_plan_requires_criteria_row(engine):
    with Session(engine) as session:
        user = make_user(session)
        job = make_job(session, "1", "Senior Python Engineer", jd="Build Python services.")
        add_decision(session, user.id, job, TITLE_JUDGE, score=1)

    assert plan_judge_jd(engine) == []


def test_execute_writes_decisions_via_injected_judge(engine):
    with Session(engine) as session:
        user, job_pass, _ = _seed(session)
        add_decision(session, user.id, job_pass, TITLE_JUDGE, score=1)

    plans = plan_judge_jd(engine)

    def stub_judge(plan: JudgeJdPlan) -> JdVerdict:
        return JdVerdict(passes=False, reason="requires on-call rotation")

    results = list(execute_judge_jd_plan(engine, plans, judge=stub_judge))
    assert len(results) == 1

    with Session(engine) as session:
        rows = session.exec(select(Decision).where(Decision.step == STEP)).all()
        assert len(rows) == 1
        assert rows[0].score == 0
        assert rows[0].reason == "requires on-call rotation"


def test_execute_pass_clears_reason(engine):
    with Session(engine) as session:
        user, job_pass, _ = _seed(session)
        add_decision(session, user.id, job_pass, TITLE_JUDGE, score=1)

    plans = plan_judge_jd(engine)

    def stub_judge(plan: JudgeJdPlan) -> JdVerdict:
        return JdVerdict(passes=True, reason="great fit")

    results = list(execute_judge_jd_plan(engine, plans, judge=stub_judge))
    assert len(results) == 1
    assert results[0].passes is True

    with Session(engine) as session:
        row = session.exec(select(Decision).where(Decision.step == STEP)).one()
        assert row.score == 1
        assert row.reason is None


def _seed_eval_user(
    session: Session, name: str = "Alice", criteria: str = "Python backend roles."
):
    user = make_user(session, name=name)
    session.add(Criteria(user_id=user.id, criteria=criteria))
    session.commit()
    return user


def _add_jd_decision(
    session: Session,
    user_id,
    job,
    *,
    score: int,
    reason: str | None,
    judged_at: datetime,
) -> None:
    session.add(
        Decision(
            user_id=user_id,
            source_name=job.source_name,
            source_id=job.source_id,
            step=STEP,
            score=score,
            reason=reason,
            judged_at=judged_at,
        )
    )
    session.commit()


def test_eval_groups_by_user(engine):
    with Session(engine) as session:
        alice = _seed_eval_user(session, name="Alice", criteria="Python roles.")
        bob = _seed_eval_user(session, name="Bob", criteria="Frontend roles.")
        job_a = make_job(session, "1", "Senior Python Engineer", jd="Python.")
        job_b = make_job(session, "2", "Marketing Manager", jd="Marketing.")
        add_decision(session, alice.id, job_a, STEP, score=1)
        add_decision(session, bob.id, job_b, STEP, score=0, reason="not engineering")

    users = plan_judge_jd_eval(engine)
    assert [u.user_name for u in users] == ["Alice", "Bob"]

    a, b = users
    assert [(e.source_id, e.passes, e.reason) for e in a.entries] == [("1", True, None)]
    assert [(e.source_id, e.passes, e.reason) for e in b.entries] == [
        ("2", False, "not engineering"),
    ]


def test_eval_sorts_entries_by_judged_at_desc(engine):
    with Session(engine) as session:
        alice = _seed_eval_user(session)
        job_old = make_job(session, "1", "Old Job", jd="old")
        job_new = make_job(session, "2", "New Job", jd="new")
        _add_jd_decision(
            session, alice.id, job_old,
            score=1, reason=None,
            judged_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        _add_jd_decision(
            session, alice.id, job_new,
            score=1, reason=None,
            judged_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )

    users = plan_judge_jd_eval(engine)
    assert [e.source_id for e in users[0].entries] == ["2", "1"]


def test_render_judge_jd_plan_returns_grouped_text(engine):
    with Session(engine) as session:
        user, job_pass, _ = _seed(session)
        add_decision(session, user.id, job_pass, TITLE_JUDGE, score=1)

    plans = plan_judge_jd(engine)
    report = render_judge_jd_plan(plans)

    assert "Alice" in report
    assert "to judge: 1" in report
    assert "Senior Python Engineer" in report
