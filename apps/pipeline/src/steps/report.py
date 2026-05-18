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
from models import ReportSend, User
from steps import PIPELINE_STEPS


@dataclass
class FunnelStage:
    label: str
    count: int


@dataclass
class UserReport:
    user_id: UUID
    user_name: str
    user_email: str
    jobs: list[Job] = field(default_factory=list)
    funnel: list[FunnelStage] = field(default_factory=list)
    cutoff_at: datetime | None = None


_FUNNEL_LABELS = {
    "title_filter": "Filter",
    "title_judge": "Judge",
    "jd_judge": "Selected",
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
        decisions = session.exec(
            select(
                Decision.user_id,
                Decision.source_name,
                Decision.source_id,
                Decision.step,
                Decision.score,
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
    seen_ranks = [step_rank[step] for _, _, _, step, _, _ in decisions if step in step_rank]
    reports = [
        UserReport(user_id=u.id, user_name=u.name, user_email=u.email) for u in users
    ]
    if not seen_ranks:
        return reports

    target_step = PIPELINE_STEPS[max(seen_ranks)]
    first_step = PIPELINE_STEPS[0]
    by_user: dict[UUID, list[Job]] = {}
    max_judged: dict[UUID, datetime] = {}
    saw_counts: dict[UUID, int] = {}
    pass_counts: dict[UUID, dict[str, int]] = {}
    for uid, source_name, source_id, step, score, judged_at in decisions:
        judged_at = _as_utc(judged_at)
        cutoff = latest_cutoffs.get(uid)
        if cutoff is not None and judged_at <= cutoff:
            continue
        if step == first_step:
            saw_counts[uid] = saw_counts.get(uid, 0) + 1
        if score == 1 and step in step_rank:
            pass_counts.setdefault(uid, {})[step] = (
                pass_counts.setdefault(uid, {}).get(step, 0) + 1
            )
        if step != target_step or score != 1:
            continue
        job = jobs.get((source_name, source_id))
        if job is None:
            continue
        by_user.setdefault(uid, []).append(job)
        current_max = max_judged.get(uid)
        if current_max is None or judged_at > current_max:
            max_judged[uid] = judged_at

    for report in reports:
        report.jobs = by_user.get(report.user_id, [])
        report.cutoff_at = max_judged.get(report.user_id)
        user_passes = pass_counts.get(report.user_id, {})
        report.funnel = [FunnelStage("Saw", saw_counts.get(report.user_id, 0))] + [
            FunnelStage(_FUNNEL_LABELS[step], user_passes.get(step, 0))
            for step in PIPELINE_STEPS
        ]
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


def _report_markdown(report: UserReport, now: datetime) -> str:
    lines = [f"# Jobs for {report.user_name} ({report.user_email})", ""]
    if not report.jobs:
        lines += ["_No surviving jobs._", ""]
        return "\n".join(lines)
    for job in report.jobs:
        title = job.title or "(no title)"
        url = job.url or ""
        heading = f"[{title}]({url})" if url else title
        lines.append(
            f"- **{heading}** — {job.source_name} · {_ago(job.published_at, now)}"
        )
    lines.append("")
    return "\n".join(lines)


def render_report_preview(reports: list[UserReport]) -> str:
    now = datetime.now(timezone.utc)
    return "\n\n".join(_report_markdown(report, now) for report in reports)


_jinja_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=select_autoescape(default=True),
)


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
