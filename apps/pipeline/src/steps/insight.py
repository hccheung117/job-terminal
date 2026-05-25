from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Callable

import llm
from paths import PROMPTS_DIR
from steps.report import ReportInsightInput, UserReport

MODEL = os.environ["SMALL_MODEL"]
PROMPT_TEMPLATE = (PROMPTS_DIR / "report_insight.md").read_text(encoding="utf-8")

InsightJudge = Callable[[ReportInsightInput], str]


def canonical_payload(inp: ReportInsightInput) -> str:
    return json.dumps(asdict(inp), sort_keys=True, default=str, separators=(",", ":"))


def insight_cache_path(cache_dir: Path, inp: ReportInsightInput) -> Path:
    digest = hashlib.sha256(canonical_payload(inp).encode("utf-8")).hexdigest()
    return Path(cache_dir) / f"{digest}.md"


def _format_funnel_block(inp: ReportInsightInput) -> str:
    f = inp.funnel
    lines = [
        f"Funnel: {f.seen} seen, {f.kept} kept, {f.shortlisted} shortlisted, {f.picked} picked",
        f"Effort saved: {inp.removed_total} roles removed before the final reading list",
        f"Removed by title filter: {inp.removed_by_title_filter}",
        f"Removed by title judgment: {inp.removed_by_title_judge}",
        f"Removed by JD judgment: {inp.removed_by_jd_judge}",
    ]
    if inp.picked:
        lines.append("Picked titles:")
        for p in inp.picked:
            lines.append(f"- {p.title}")
    if inp.rejected:
        lines.append("Rejected examples:")
        labels = {
            "title_filter": "removed by title filter",
            "title_judge": "removed after title review",
            "jd_judge": "removed after JD review",
        }
        for r in inp.rejected[:5]:
            label = labels.get(r.failed_step, f"removed at {r.failed_step}")
            reason = r.reason or "no reason given"
            lines.append(f"- {r.title}; {label}; reason: {reason}")
    return "\n".join(lines)


def _default_judge(inp: ReportInsightInput) -> str:
    prompt = PROMPT_TEMPLATE.format(
        criteria=inp.criteria or "(none)",
        funnel_block=_format_funnel_block(inp),
    )
    msg = llm.openai(MODEL).invoke(prompt)
    text = getattr(msg, "content", msg)
    if isinstance(text, list):
        text = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in text
        )
    return str(text)


def generate_insight(
    inp: ReportInsightInput,
    *,
    cache_dir: Path,
    judge: InsightJudge | None = None,
) -> str | None:
    cache_dir = Path(cache_dir)
    path = insight_cache_path(cache_dir, inp)
    try:
        if path.is_file():
            cached = path.read_text(encoding="utf-8").strip()
            if cached:
                return cached
    except OSError:
        pass

    judge_fn = judge or _default_judge
    try:
        text = judge_fn(inp)
    except Exception:
        return None
    if not text or not text.strip():
        return None
    text = text.strip()
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return text


def apply_insights(
    reports: list[UserReport],
    *,
    cache_dir: Path,
    judge: InsightJudge | None = None,
) -> None:
    for report in reports:
        if report.insight_input is None:
            continue
        report.insight = generate_insight(
            report.insight_input, cache_dir=cache_dir, judge=judge
        )
