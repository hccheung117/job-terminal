import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from steps.report import (
    FunnelCounts,
    PickedJob,
    RejectedJob,
    ReportInsightInput,
    UserReport,
)
from steps.insight import (
    apply_insights,
    canonical_payload,
    generate_insight,
    insight_cache_path,
)


def _input(user_name: str = "Alice") -> ReportInsightInput:
    return ReportInsightInput(
        user_name=user_name,
        criteria="Senior Python",
        window_start=datetime(2026, 5, 17, 11, tzinfo=timezone.utc),
        window_end=datetime(2026, 5, 17, 13, tzinfo=timezone.utc),
        funnel=FunnelCounts(seen=7, kept=5, shortlisted=5, picked=4),
        picked=[
            PickedJob(
                title="Risk Analyst",
                source_name="linkedin",
                source_id="1",
                url="https://x",
                location="NYC",
                groups=["g"],
                published_age="2h ago",
                jd_available=True,
            )
        ],
        rejected=[
            RejectedJob(
                title="Compliance Officer",
                source_name="linkedin",
                source_id="2",
                failed_step="jd_judge",
                reason="seniority mismatch",
                location="NYC",
                groups=["g"],
            )
        ],
        removed_total=3,
        removed_by_title_filter=2,
        removed_by_title_judge=0,
        removed_by_jd_judge=1,
    )


def test_canonical_payload_is_stable_and_sorted():
    a = canonical_payload(_input())
    b = canonical_payload(_input())
    assert a == b
    parsed = json.loads(a)
    assert list(parsed.keys()) == sorted(parsed.keys())


def test_canonical_payload_changes_when_input_changes():
    base = _input()
    other = _input()
    other.funnel = FunnelCounts(seen=8, kept=5, shortlisted=5, picked=4)
    assert canonical_payload(base) != canonical_payload(other)


def test_cache_hit_skips_llm(tmp_path: Path):
    inp = _input()
    path = insight_cache_path(tmp_path, inp)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("CACHED PARAGRAPH")
    calls: list[int] = []

    def judge(_inp: ReportInsightInput) -> str:
        calls.append(1)
        return "LIVE"

    text = generate_insight(inp, cache_dir=tmp_path, judge=judge)
    assert text == "CACHED PARAGRAPH"
    assert calls == []


def test_cache_miss_calls_llm_and_writes_file(tmp_path: Path):
    inp = _input()
    text = generate_insight(inp, cache_dir=tmp_path, judge=lambda _i: "LIVE PARAGRAPH")
    assert text == "LIVE PARAGRAPH"
    path = insight_cache_path(tmp_path, inp)
    assert path.read_text() == "LIVE PARAGRAPH"


def test_changed_input_uses_different_cache_path(tmp_path: Path):
    a = _input()
    b = _input()
    b.funnel = FunnelCounts(seen=8, kept=5, shortlisted=5, picked=4)
    assert insight_cache_path(tmp_path, a) != insight_cache_path(tmp_path, b)


def test_generate_returns_none_when_judge_raises(tmp_path: Path):
    def judge(_i: ReportInsightInput) -> str:
        raise RuntimeError("boom")
    assert generate_insight(_input(), cache_dir=tmp_path, judge=judge) is None


def test_generate_returns_none_when_judge_returns_empty(tmp_path: Path):
    assert generate_insight(_input(), cache_dir=tmp_path, judge=lambda _i: "  ") is None


def test_apply_insights_sets_paragraph_only_when_input_present(tmp_path: Path):
    r1 = UserReport(user_id=uuid4(), user_name="A", user_email="a@x")
    r2 = UserReport(user_id=uuid4(), user_name="B", user_email="b@x")
    r1.insight_input = _input("A")
    apply_insights([r1, r2], cache_dir=tmp_path, judge=lambda _i: "PARA")
    assert r1.insight == "PARA"
    assert r2.insight is None


def test_apply_insights_swallows_cache_write_errors(tmp_path: Path):
    inp = _input()
    r = UserReport(user_id=uuid4(), user_name="A", user_email="a@x")
    r.insight_input = inp
    bad = tmp_path / "afile"
    bad.write_text("x")
    apply_insights([r], cache_dir=bad, judge=lambda _i: "PARA")
    assert r.insight == "PARA"
