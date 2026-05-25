import os
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from job_terminal_tui import TuiFormatter
from pydantic import BaseModel, Field as PydField
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import llm
from db import dialect_insert
from job_terminal_models import Decision, Job
from models import Criteria, User
from paths import PROMPTS_DIR
from steps.judge_title import STEP as TITLE_JUDGE_STEP

STEP = "jd_judge"
MODEL = os.environ["SMALL_MODEL"]

PROMPT_TEMPLATE = (PROMPTS_DIR / "judge_jd.md").read_text(encoding="utf-8")


@dataclass
class JudgeJdPlan:
    user_id: UUID
    user_name: str
    user_email: str
    criteria: str
    source_name: str
    source_id: str
    title: str
    jd: str


@dataclass
class JudgeJdResult:
    plan: JudgeJdPlan
    passes: bool
    reason: str


@dataclass
class JudgeJdEvalEntry:
    source_name: str
    source_id: str
    title: str
    jd: str
    passes: bool
    reason: str | None
    judged_at: datetime


@dataclass
class JudgeJdEvalUser:
    user_id: UUID
    user_name: str
    user_email: str
    criteria: str
    entries: list[JudgeJdEvalEntry]


class JdVerdict(BaseModel):
    passes: bool = PydField(description="True if the job passes the user's criteria.")
    reason: str = PydField(description="Concise reason for the decision.")


JdJudge = Callable[[JudgeJdPlan], JdVerdict]


def plan_judge_jd(engine: Engine) -> list[JudgeJdPlan]:
    with Session(engine) as session:
        users = {u.id: u for u in session.exec(select(User)).all()}
        criteria_rows = session.exec(select(Criteria)).all()
        jobs = {(j.source_name, j.source_id): j for j in session.exec(select(Job)).all()}

        passed_title_judge = set(
            session.exec(
                select(Decision.user_id, Decision.source_name, Decision.source_id)
                .where(Decision.step == TITLE_JUDGE_STEP)
                .where(Decision.score == 1)
            ).all()
        )
        already_judged = set(
            session.exec(
                select(Decision.user_id, Decision.source_name, Decision.source_id).where(
                    Decision.step == STEP
                )
            ).all()
        )

    plans: list[JudgeJdPlan] = []
    for c in criteria_rows:
        user = users.get(c.user_id)
        if user is None:
            continue
        for (uid, source_name, source_id) in passed_title_judge:
            if uid != c.user_id:
                continue
            if (uid, source_name, source_id) in already_judged:
                continue
            job = jobs.get((source_name, source_id))
            if job is None or not job.title or not job.jd:
                continue
            plans.append(
                JudgeJdPlan(
                    user_id=user.id,
                    user_name=user.name,
                    user_email=user.email,
                    criteria=c.criteria,
                    source_name=source_name,
                    source_id=source_id,
                    title=job.title,
                    jd=job.jd,
                )
            )
    return plans


def _default_judge(plan: JudgeJdPlan) -> JdVerdict:
    prompt = PROMPT_TEMPLATE.format(criteria=plan.criteria, title=plan.title, jd=plan.jd)
    return llm.judge(llm.openai(MODEL), prompt, JdVerdict)


def execute_judge_jd_plan(
    engine: Engine,
    plans: list[JudgeJdPlan],
    judge: JdJudge = _default_judge,
) -> Generator[JudgeJdResult, None, None]:
    insert = dialect_insert(engine)
    for plan in plans:
        verdict = judge(plan)
        result = JudgeJdResult(
            plan=plan, passes=verdict.passes, reason=verdict.reason
        )
        judged_at = datetime.now(timezone.utc)
        row = {
            "user_id": result.plan.user_id,
            "source_name": result.plan.source_name,
            "source_id": result.plan.source_id,
            "step": STEP,
            "score": 1 if result.passes else 0,
            "reason": None if result.passes else result.reason,
            "judged_at": judged_at,
        }
        stmt = insert(Decision).values([row]).on_conflict_do_nothing(
            index_elements=["user_id", "source_name", "source_id", "step"],
        )
        with Session(engine) as session:
            session.exec(stmt)
            session.commit()
        yield result


def render_judge_jd_plan(plans: list[JudgeJdPlan]) -> str:
    fmt = TuiFormatter()
    by_user: dict[UUID, list[JudgeJdPlan]] = {}
    for p in plans:
        by_user.setdefault(p.user_id, []).append(p)

    for user_plans in by_user.values():
        head = user_plans[0]
        fmt.header(f"{head.user_name} ({TuiFormatter.dim(head.user_email)})")
        fmt.info(f"to judge: {len(user_plans)}", indent=2)
        for p in user_plans:
            fmt.info(p.title, indent=2)
    return fmt.render()


def plan_judge_jd_eval(engine: Engine) -> list[JudgeJdEvalUser]:
    with Session(engine) as session:
        users = {u.id: u for u in session.exec(select(User)).all()}
        criteria_rows = session.exec(select(Criteria)).all()
        jobs = {(j.source_name, j.source_id): j for j in session.exec(select(Job)).all()}
        decisions = session.exec(
            select(
                Decision.user_id,
                Decision.source_name,
                Decision.source_id,
                Decision.score,
                Decision.reason,
                Decision.judged_at,
            ).where(Decision.step == STEP)
        ).all()

    entries_by_user: dict[UUID, list[JudgeJdEvalEntry]] = {}
    for user_id, source_name, source_id, score, reason, judged_at in decisions:
        job = jobs.get((source_name, source_id))
        if job is None or not job.title:
            continue
        entries_by_user.setdefault(user_id, []).append(
            JudgeJdEvalEntry(
                source_name=source_name,
                source_id=source_id,
                title=job.title,
                jd=job.jd or "",
                passes=score == 1,
                reason=reason,
                judged_at=judged_at,
            )
        )

    result: list[JudgeJdEvalUser] = []
    for c in criteria_rows:
        user = users.get(c.user_id)
        if user is None:
            continue
        entries = entries_by_user.get(user.id, [])
        entries.sort(key=lambda e: e.judged_at, reverse=True)
        result.append(
            JudgeJdEvalUser(
                user_id=user.id,
                user_name=user.name,
                user_email=user.email,
                criteria=c.criteria,
                entries=entries,
            )
        )
    result.sort(key=lambda u: u.user_name)
    return result


def render_judge_jd_eval(
    users: list[JudgeJdEvalUser], job: tuple[str, str] | None = None
) -> str:
    sections: list[str] = []
    for user in users:
        entries = user.entries
        if job is not None:
            entries = [
                e for e in entries if (e.source_name, e.source_id) == job
            ]
            if not entries:
                continue
        lines = [
            f"# {user.user_name} ({user.user_email})",
            "",
            user.criteria,
        ]
        if not entries and job is None:
            lines.append("- _no past judgments_")
        for entry in entries:
            verdict = "pass" if entry.passes else f"reject: {entry.reason}"
            lines.append(
                f"- {entry.source_name}/{entry.source_id}  {entry.title} — {verdict}"
            )
            if job is not None and entry.jd:
                lines.append("")
                lines.append("  <jd>")
                for jd_line in entry.jd.splitlines() or [""]:
                    lines.append(f"  {jd_line}")
                lines.append("  </jd>")
                lines.append("")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
