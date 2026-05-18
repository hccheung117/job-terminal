from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cli import app

runner = CliRunner()


@patch("commands.eval.render_judge_title_eval")
@patch("commands.eval.plan_judge_title_eval")
@patch("commands.eval.build_engine")
def test_eval_title_judge_dispatches(mock_build_engine, mock_plan, mock_render):
    engine = MagicMock()
    mock_build_engine.return_value = engine
    users = [MagicMock()]
    mock_plan.return_value = users

    result = runner.invoke(app, ["eval", "title-judge"])

    assert result.exit_code == 0, result.output
    mock_build_engine.assert_called_once()
    mock_plan.assert_called_once_with(engine)
    mock_render.assert_called_once_with(users)


def test_title_judge_rejects_eval_flag():
    result = runner.invoke(app, ["title", "judge", "--eval"])

    assert result.exit_code != 0
