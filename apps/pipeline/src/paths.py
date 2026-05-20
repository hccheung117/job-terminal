from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
ENV_FILE = APP_ROOT / ".env"
REPO_ROOT = APP_ROOT.parent.parent
INSIGHTS_DIR = REPO_ROOT / "data" / "insights"
