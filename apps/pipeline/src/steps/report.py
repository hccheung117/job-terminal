import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

import resend
from markdown_it import MarkdownIt
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from job_terminal_models import Decision, Job
from models import User
from steps import PIPELINE_STEPS


@dataclass
class UserReport:
    user_id: UUID
    user_name: str
    user_email: str
    jobs: list[Job] = field(default_factory=list)


@dataclass
class ReportSendFailure:
    batch_index: int
    message: str


@dataclass
class ReportSendResult:
    sent: int
    failures: list[ReportSendFailure]


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
            )
        ).all()

    step_rank = {s: i for i, s in enumerate(PIPELINE_STEPS)}
    seen_ranks = [step_rank[step] for _, _, _, step, _ in decisions if step in step_rank]
    reports = [
        UserReport(user_id=u.id, user_name=u.name, user_email=u.email) for u in users
    ]
    if not seen_ranks:
        return reports

    target_step = PIPELINE_STEPS[max(seen_ranks)]
    by_user: dict[UUID, list[Job]] = {}
    for uid, source_name, source_id, step, score in decisions:
        if step != target_step or score != 1:
            continue
        job = jobs.get((source_name, source_id))
        if job is not None:
            by_user.setdefault(uid, []).append(job)

    for report in reports:
        report.jobs = by_user.get(report.user_id, [])
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


def execute_report_plan(engine: Engine, reports: list[UserReport]) -> ReportSendResult:
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise ValueError("RESEND_API_KEY is not set")
    resend.api_key = api_key

    md = MarkdownIt()
    now = datetime.now(timezone.utc)
    
    # In production, use your own verified domain instead of onboarding@resend.dev
    from_email = os.environ.get("RESEND_FROM_EMAIL")
    
    params = []
    for report in reports:
        if not report.jobs:
            continue
        markdown = _report_markdown(report, now)
        html = md.render(markdown)
        params.append(
            {
                "from": from_email,
                "to": report.user_email,
                "subject": f"Jobs for {report.user_name}",
                "html": html,
            }
        )

    sent = 0
    failures: list[ReportSendFailure] = []
    # Resend batch API supports up to 100 emails per request
    batch_size = 100
    for i in range(0, len(params), batch_size):
        batch = params[i:i + batch_size]
        batch_index = i // batch_size
        try:
            resend.Batch.send(batch)
            sent += len(batch)
        except Exception as exc:
            failures.append(ReportSendFailure(batch_index=batch_index, message=str(exc)))

    return ReportSendResult(sent=sent, failures=failures)
