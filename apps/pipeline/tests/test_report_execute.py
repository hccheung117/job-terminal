from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from sqlmodel import Session, select

from conftest import make_job, make_user
from models import ReportSend
from steps.report import (
    ReportSendFailure,
    ReportSendResult,
    UserReport,
    execute_report_plan,
)


def _env():
    return patch.dict(
        "os.environ",
        {"RESEND_API_KEY": "test", "RESEND_FROM_EMAIL": "from@test"},
    )


def test_execute_skips_users_with_no_jobs(engine) -> None:
    reports = [
        UserReport(
            user_id=uuid4(),
            user_name="Alice",
            user_email="alice@example.com",
            jobs=[],
            cutoff_at=None,
        )
    ]
    with _env():
        result = execute_report_plan(engine, reports)
    assert result == ReportSendResult(sent=0, failures=[])

    with Session(engine) as session:
        rows = session.exec(select(ReportSend)).all()
    assert rows == []


def test_execute_writes_report_send_on_success(engine) -> None:
    cutoff = datetime(2026, 5, 17, 13, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        user = make_user(session)
        job = make_job(session, "1", "Senior Python Engineer")
    reports = [
        UserReport(
            user_id=user.id,
            user_name=user.name,
            user_email=user.email,
            jobs=[job],
            cutoff_at=cutoff,
        )
    ]
    with _env(), patch("steps.report.resend.Emails.send", return_value={"id": "ok"}) as send:
        result = execute_report_plan(engine, reports)
    assert send.call_count == 1
    assert result.sent == 1
    assert result.failures == []
    with Session(engine) as session:
        rows = session.exec(select(ReportSend)).all()
    assert len(rows) == 1
    assert rows[0].user_id == user.id
    assert rows[0].cutoff_at == cutoff


def test_execute_does_not_write_cursor_on_failure(engine) -> None:
    cutoff = datetime(2026, 5, 17, 13, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        user = make_user(session)
        job = make_job(session, "1", "Senior Python Engineer")
    reports = [
        UserReport(
            user_id=user.id,
            user_name=user.name,
            user_email=user.email,
            jobs=[job],
            cutoff_at=cutoff,
        )
    ]
    with _env(), patch(
        "steps.report.resend.Emails.send", side_effect=RuntimeError("boom")
    ):
        result = execute_report_plan(engine, reports)
    assert result.sent == 0
    assert result.failures == [
        ReportSendFailure(user_id=user.id, message="boom")
    ]
    with Session(engine) as session:
        rows = session.exec(select(ReportSend)).all()
    assert rows == []


def test_execute_advances_cursor_only_for_successful_users(engine) -> None:
    cutoff = datetime(2026, 5, 17, 13, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        good = make_user(session, name="Alice")
        bad = make_user(session, name="Bob", email="bob@example.com")
        job = make_job(session, "1", "Senior Python Engineer")
    reports = [
        UserReport(
            user_id=good.id,
            user_name=good.name,
            user_email=good.email,
            jobs=[job],
            cutoff_at=cutoff,
        ),
        UserReport(
            user_id=bad.id,
            user_name=bad.name,
            user_email=bad.email,
            jobs=[job],
            cutoff_at=cutoff,
        ),
    ]

    def fake_send(params):
        if params["to"] == bad.email:
            raise RuntimeError("nope")
        return {"id": "ok"}

    with _env(), patch("steps.report.resend.Emails.send", side_effect=fake_send):
        result = execute_report_plan(engine, reports)

    assert result.sent == 1
    assert result.failures == [
        ReportSendFailure(user_id=bad.id, message="nope")
    ]
    with Session(engine) as session:
        rows = session.exec(select(ReportSend)).all()
    assert [r.user_id for r in rows] == [good.id]
