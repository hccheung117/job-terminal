from steps.judge_title import render_judge_title_eval
from steps.judge_title import JudgeTitleEvalEntry, JudgeTitleEvalUser
from datetime import datetime, timezone
from uuid import uuid4


def test_render_judge_title_eval_returns_markdown() -> None:
    user_id = uuid4()
    users = [
        JudgeTitleEvalUser(
            user_id=user_id,
            user_name="Alice",
            user_email="alice@example.com",
            criteria="Python backend roles.",
            entries=[
                JudgeTitleEvalEntry(
                    source_name="linkedin",
                    source_id="1",
                    title="Senior Python Engineer",
                    passes=True,
                    reason=None,
                    judged_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                )
            ],
        )
    ]

    markdown = render_judge_title_eval(users)

    assert "# Alice (alice@example.com)" in markdown
    assert "Python backend roles." in markdown
    assert "Senior Python Engineer" in markdown
    assert "pass" in markdown


def test_render_judge_title_eval_no_entries() -> None:
    user_id = uuid4()
    users = [
        JudgeTitleEvalUser(
            user_id=user_id,
            user_name="Alice",
            user_email="alice@example.com",
            criteria="Python backend roles.",
            entries=[],
        )
    ]

    markdown = render_judge_title_eval(users)

    assert "_no past judgments_" in markdown
