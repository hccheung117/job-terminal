from datetime import datetime, timezone

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
    plan_judge_title_eval,
    render_judge_title_plan,
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

    results = list(execute_judge_title_plan(engine, plans, judge=stub_judge))
    assert len(results) == 1

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

    results = list(execute_judge_title_plan(engine, plans, judge=stub_judge))
    assert len(results) == 1
    assert results[0].passes is True

    with Session(engine) as session:
        row = session.exec(select(Decision).where(Decision.step == STEP)).one()
        assert row.score == 1
        assert row.reason is None


def test_execute_commits_each_result_before_next(engine):
    with Session(engine) as session:
        user = make_user(session)
        job_one = make_job(session, "1", "Senior Python Engineer")
        job_two = make_job(session, "2", "Staff Python Engineer")
        session.add(Criteria(user_id=user.id, criteria="I want Python backend roles."))
        session.commit()
        add_decision(session, user.id, job_one, "title_filter", score=1)
        add_decision(session, user.id, job_two, "title_filter", score=1)

    plans = plan_judge_title(engine)
    assert len(plans) == 2

    call_count = 0

    def stub_judge(plan: JudgeTitlePlan) -> TitleVerdict:
        nonlocal call_count
        call_count += 1
        with Session(engine) as session:
            rows = session.exec(select(Decision).where(Decision.step == STEP)).all()
        if call_count == 1:
            assert len(rows) == 0
            return TitleVerdict(passes=True, reason="looks like a fit")
        assert len(rows) == 1
        return TitleVerdict(passes=False, reason="not senior enough")

    results = list(execute_judge_title_plan(engine, plans, judge=stub_judge))
    assert len(results) == 2
    assert results[0].passes is True
    assert results[1].passes is False

    with Session(engine) as session:
        rows = session.exec(
            select(Decision).where(Decision.step == STEP).order_by(Decision.source_id)
        ).all()
        assert len(rows) == 2


def _seed_eval_user(
    session: Session, name: str = "Alice", criteria: str = "Python backend roles."
):
    user = make_user(session, name=name)
    session.add(Criteria(user_id=user.id, criteria=criteria))
    session.commit()
    return user


def _add_judge_decision(
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
        job_a = make_job(session, "1", "Senior Python Engineer")
        job_b = make_job(session, "2", "Marketing Manager")
        add_decision(session, alice.id, job_a, STEP, score=1)
        add_decision(session, bob.id, job_b, STEP, score=0, reason="not engineering")

    users = plan_judge_title_eval(engine)
    assert [u.user_name for u in users] == ["Alice", "Bob"]

    a, b = users
    assert a.criteria == "Python roles."
    assert [(e.source_id, e.title, e.passes, e.reason) for e in a.entries] == [
        ("1", "Senior Python Engineer", True, None),
    ]
    assert b.criteria == "Frontend roles."
    assert [(e.source_id, e.title, e.passes, e.reason) for e in b.entries] == [
        ("2", "Marketing Manager", False, "not engineering"),
    ]


def test_eval_sorts_entries_by_judged_at_desc(engine):
    with Session(engine) as session:
        alice = _seed_eval_user(session)
        job_old = make_job(session, "1", "Old Job")
        job_new = make_job(session, "2", "New Job")
        _add_judge_decision(
            session, alice.id, job_old,
            score=1, reason=None,
            judged_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        _add_judge_decision(
            session, alice.id, job_new,
            score=1, reason=None,
            judged_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )

    users = plan_judge_title_eval(engine)
    assert [e.source_id for e in users[0].entries] == ["2", "1"]


def test_eval_skips_other_steps(engine):
    with Session(engine) as session:
        alice = _seed_eval_user(session)
        job = make_job(session, "1", "Senior Python Engineer")
        add_decision(session, alice.id, job, "title_filter", score=1)

    users = plan_judge_title_eval(engine)
    assert len(users) == 1
    assert users[0].entries == []


def test_eval_includes_users_with_no_decisions(engine):
    with Session(engine) as session:
        _seed_eval_user(session)

    users = plan_judge_title_eval(engine)
    assert len(users) == 1
    assert users[0].entries == []


def test_render_judge_title_plan_returns_grouped_text(engine):
    with Session(engine) as session:
        user, job_pass, _ = _seed(session)
        add_decision(session, user.id, job_pass, "title_filter", score=1)

    plans = plan_judge_title(engine)
    report = render_judge_title_plan(plans)

    assert "Alice" in report
    assert "to judge: 1" in report
    assert "Senior Python Engineer" in report
    assert "linkedin/" not in report
