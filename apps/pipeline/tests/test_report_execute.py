from unittest.mock import patch

from steps.report import ReportSendResult, UserReport, execute_report_plan
from uuid import uuid4


def test_execute_report_plan_returns_failures() -> None:
    user_id = uuid4()
    reports = [
        UserReport(
            user_id=user_id,
            user_name="Alice",
            user_email="alice@example.com",
            jobs=[],
        )
    ]

    with patch.dict("os.environ", {"RESEND_API_KEY": "test", "RESEND_FROM_EMAIL": "from@test"}):
        result = execute_report_plan(None, reports)

    assert result == ReportSendResult(sent=0, failures=[])
