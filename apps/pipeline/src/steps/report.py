import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape
from mjml import mjml2html
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from job_terminal_models import Decision, Job
from models import Criteria, ReportSend, User
from steps import PIPELINE_STEPS


@dataclass
class FunnelStage:
    label: str
    count: int


@dataclass
class FunnelCounts:
    seen: int
    kept: int
    shortlisted: int
    picked: int


@dataclass
class PickedJob:
    title: str
    source_name: str
    source_id: str
    url: str | None
    location: str | None
    groups: list[str]
    published_age: str
    jd_available: bool


@dataclass
class RejectedJob:
    title: str
    source_name: str
    source_id: str
    failed_step: str
    reason: str | None
    location: str | None
    groups: list[str]


@dataclass
class ReportInsightInput:
    user_name: str
    criteria: str
    window_start: datetime | None
    window_end: datetime | None
    funnel: FunnelCounts
    picked: list[PickedJob]
    rejected: list[RejectedJob]
    removed_total: int
    removed_by_title_filter: int
    removed_by_title_judge: int
    removed_by_jd_judge: int


@dataclass
class UserReport:
    user_id: UUID
    user_name: str
    user_email: str
    jobs: list[Job] = field(default_factory=list)
    funnel: list[FunnelStage] = field(default_factory=list)
    cutoff_at: datetime | None = None
    insight_input: ReportInsightInput | None = None
    insight: str | None = None


_FUNNEL_LABELS = {
    "title_filter": "Kept",
    "title_judge": "Shortlisted",
    "jd_judge": "Picked",
}


@dataclass
class ReportSendFailure:
    user_id: UUID
    message: str


@dataclass
class ReportSendResult:
    sent: int
    failures: list[ReportSendFailure]


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def plan_report(engine: Engine) -> list[UserReport]:
    with Session(engine) as session:
        users = session.exec(select(User)).all()
        jobs = {(j.source_name, j.source_id): j for j in session.exec(select(Job)).all()}
        criteria = {c.user_id: c.criteria for c in session.exec(select(Criteria)).all()}
        decisions = session.exec(
            select(
                Decision.user_id,
                Decision.source_name,
                Decision.source_id,
                Decision.step,
                Decision.score,
                Decision.reason,
                Decision.judged_at,
            )
        ).all()
        latest_cutoffs: dict[UUID, datetime] = {}
        for uid, cutoff in session.exec(
            select(ReportSend.user_id, ReportSend.cutoff_at)
        ).all():
            current = latest_cutoffs.get(uid)
            if current is None or cutoff > current:
                latest_cutoffs[uid] = cutoff

    step_rank = {s: i for i, s in enumerate(PIPELINE_STEPS)}
    in_window = [
        (uid, src, sid, step, score, reason, _as_utc(judged_at))
        for uid, src, sid, step, score, reason, judged_at in decisions
        if (latest_cutoffs.get(uid) is None or _as_utc(judged_at) > latest_cutoffs[uid])
    ]
    reports = [
        UserReport(user_id=u.id, user_name=u.name, user_email=u.email) for u in users
    ]
    if not in_window:
        return reports

    seen_ranks = [step_rank[step] for _, _, _, step, _, _, _ in in_window if step in step_rank]
    if not seen_ranks:
        return reports
    target_step = PIPELINE_STEPS[max(seen_ranks)]
    first_step = PIPELINE_STEPS[0]

    by_user: dict[UUID, list[Job]] = {}
    pick_max_judged: dict[UUID, datetime] = {}
    window_min: dict[UUID, datetime] = {}
    window_max: dict[UUID, datetime] = {}
    saw_counts: dict[UUID, int] = {}
    pass_counts: dict[UUID, dict[str, int]] = {}
    fail_counts: dict[UUID, dict[str, int]] = {}
    rejected_by_user: dict[UUID, list[RejectedJob]] = {}
    user_seen: set[UUID] = set()

    for uid, src, sid, step, score, reason, judged_at in in_window:
        user_seen.add(uid)
        if step == first_step:
            saw_counts[uid] = saw_counts.get(uid, 0) + 1
        if step in step_rank:
            bucket = pass_counts if score == 1 else fail_counts
            bucket.setdefault(uid, {})[step] = bucket.setdefault(uid, {}).get(step, 0) + 1
        cur_min = window_min.get(uid)
        if cur_min is None or judged_at < cur_min:
            window_min[uid] = judged_at
        cur_max = window_max.get(uid)
        if cur_max is None or judged_at > cur_max:
            window_max[uid] = judged_at
        if score == 0 and step in step_rank:
            job = jobs.get((src, sid))
            if job is not None and job.title:
                rejected_by_user.setdefault(uid, []).append(
                    RejectedJob(
                        title=job.title,
                        source_name=src,
                        source_id=sid,
                        failed_step=step,
                        reason=reason,
                        location=job.location,
                        groups=list(job.groups),
                    )
                )
        if step == target_step and score == 1:
            job = jobs.get((src, sid))
            if job is not None:
                by_user.setdefault(uid, []).append(job)
                cur = pick_max_judged.get(uid)
                if cur is None or judged_at > cur:
                    pick_max_judged[uid] = judged_at

    now = datetime.now(timezone.utc)
    for report in reports:
        report.jobs = by_user.get(report.user_id, [])
        report.cutoff_at = pick_max_judged.get(report.user_id)
        user_passes = pass_counts.get(report.user_id, {})
        report.funnel = [FunnelStage("Seen", saw_counts.get(report.user_id, 0))] + [
            FunnelStage(_FUNNEL_LABELS[step], user_passes.get(step, 0))
            for step in PIPELINE_STEPS
        ]
        if report.user_id not in user_seen:
            continue
        fails = fail_counts.get(report.user_id, {})
        f_title = fails.get("title_filter", 0)
        f_tjudge = fails.get("title_judge", 0)
        f_jd = fails.get("jd_judge", 0)
        picked_jobs = [
            PickedJob(
                title=j.title or "(no title)",
                source_name=j.source_name,
                source_id=j.source_id,
                url=j.url,
                location=j.location,
                groups=list(j.groups),
                published_age=_ago(j.published_at, now),
                jd_available=bool(j.jd),
            )
            for j in report.jobs
        ]
        report.insight_input = ReportInsightInput(
            user_name=report.user_name,
            criteria=criteria.get(report.user_id, ""),
            window_start=window_min.get(report.user_id),
            window_end=window_max.get(report.user_id),
            funnel=FunnelCounts(
                seen=saw_counts.get(report.user_id, 0),
                kept=user_passes.get("title_filter", 0),
                shortlisted=user_passes.get("title_judge", 0),
                picked=user_passes.get("jd_judge", 0),
            ),
            picked=picked_jobs,
            rejected=rejected_by_user.get(report.user_id, []),
            removed_total=f_title + f_tjudge + f_jd,
            removed_by_title_filter=f_title,
            removed_by_title_judge=f_tjudge,
            removed_by_jd_judge=f_jd,
        )
    return reports


def _ago(then: datetime | None, now: datetime) -> str:
    if then is None:
        return "unknown"
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    delta = now - then
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    if months < 12:
        return f"{months}mo ago"
    years = days // 365
    return f"{years}y ago"


_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=select_autoescape(default=True),
)


def render_report_previews(reports: list[UserReport]) -> list[tuple[UserReport, str]]:
    now = datetime.now(timezone.utc)
    return [(r, _render_email_html(r, now)) for r in reports if r.jobs]


def _render_email_html(report: UserReport, now: datetime) -> str:
    jobs = [
        {
            "title": job.title or "(no title)",
            "url": job.url or "",
            "source_name": job.source_name,
            "ago": _ago(job.published_at, now),
        }
        for job in report.jobs
    ]
    mjml_source = _jinja_env.get_template("_email.mjml").render(
        user_name=report.user_name,
        user_email=report.user_email,
        jobs=jobs,
        funnel=report.funnel,
        date=now.strftime("%a %b %-d, %Y").upper(),
        insight=report.insight,
    )
    return mjml2html(mjml_source)


def execute_report_plan(engine: Engine, reports: list[UserReport]) -> ReportSendResult:
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise ValueError("RESEND_API_KEY is not set")
    resend.api_key = api_key

    now = datetime.now(timezone.utc)
    from_email = os.environ.get("RESEND_FROM_EMAIL")
    reply_to = os.environ.get("RESEND_REPLY_TO_EMAIL")

    sent = 0
    failures: list[ReportSendFailure] = []
    for report in reports:
        if not report.jobs:
            continue
        html = _render_email_html(report, now)
        params = {
            "from": from_email,
            "to": report.user_email,
            "subject": f"Jobs for {report.user_name}",
            "html": html,
        }
        if reply_to:
            params["reply_to"] = reply_to
        try:
            resend.Emails.send(params)
        except Exception as exc:
            failures.append(ReportSendFailure(user_id=report.user_id, message=str(exc)))
            continue

        if report.cutoff_at is not None:
            with Session(engine) as session:
                session.add(
                    ReportSend(
                        user_id=report.user_id,
                        cutoff_at=report.cutoff_at,
                        sent_at=datetime.now(timezone.utc),
                    )
                )
                session.commit()
        sent += 1

    return ReportSendResult(sent=sent, failures=failures)
