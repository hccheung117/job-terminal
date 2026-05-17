import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

import resend
from markdown_it import MarkdownIt
from rich.console import Console
from rich.markdown import Markdown
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from job_terminal_models import Job
from models import Decision, User


@dataclass
class UserReport:
    user_id: UUID
    user_name: str
    user_email: str
    jobs: list[Job] = field(default_factory=list)


def plan_report(engine: Engine) -> list[UserReport]:
    with Session(engine) as session:
        users = session.exec(select(User)).all()
        jobs = session.exec(select(Job)).all()
        decided = set(
            session.exec(
                select(Decision.user_id, Decision.source_name, Decision.source_id)
            ).all()
        )

    reports = [
        UserReport(user_id=u.id, user_name=u.name, user_email=u.email) for u in users
    ]
    for report in reports:
        for job in jobs:
            if (report.user_id, job.source_name, job.source_id) in decided:
                continue
            report.jobs.append(job)
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


def render_report_preview(reports: list[UserReport]) -> None:
    now = datetime.now(timezone.utc)
    console = Console()
    for report in reports:
        console.print(Markdown(_report_markdown(report, now)))


def execute_report_plan(engine: Engine, reports: list[UserReport]) -> int:
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
    # Resend batch API supports up to 100 emails per request
    batch_size = 100
    for i in range(0, len(params), batch_size):
        batch = params[i:i + batch_size]
        try:
            resend.Batch.send(batch)
            sent += len(batch)
        except Exception as e:
            # Handle or log the error appropriately for production
            print(f"Failed to send batch {i//batch_size}: {e}")

    return sent
