from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field as PydField
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import llm
from db import dialect_insert
from job_terminal_models import Decision, Job
from models import Criteria, User
from paths import PROMPTS_DIR
from steps.filter_title import STEP as TITLE_FILTER_STEP

STEP = "title_judge"
MODEL = "gemini-3.1-flash-lite:latest"

PROMPT_TEMPLATE = (PROMPTS_DIR / "judge_title.md").read_text(encoding="utf-8")


@dataclass
class JudgeTitlePlan:
    user_id: UUID
    user_name: str
    user_email: str
    criteria: str
    source_name: str
    source_id: str
    title: str


@dataclass
class JudgeTitleResult:
    plan: JudgeTitlePlan
    passes: bool
    reason: str


@dataclass
class JudgeTitleEvalEntry:
    source_name: str
    source_id: str
    title: str
    passes: bool
    reason: str | None
    judged_at: datetime


@dataclass
class JudgeTitleEvalUser:
    user_id: UUID
    user_name: str
    user_email: str
    criteria: str
    entries: list[JudgeTitleEvalEntry]


class TitleVerdict(BaseModel):
    passes: bool = PydField(description="True if the job title passes the user's criteria.")
    reason: str = PydField(description="Concise reason for the decision.")


TitleJudge = Callable[[JudgeTitlePlan], TitleVerdict]


def plan_judge_title(engine: Engine) -> list[JudgeTitlePlan]:
    with Session(engine) as session:
        users = {u.id: u for u in session.exec(select(User)).all()}
        criteria_rows = session.exec(select(Criteria)).all()
        jobs = {(j.source_name, j.source_id): j for j in session.exec(select(Job)).all()}

        passed_filter = set(
            session.exec(
                select(Decision.user_id, Decision.source_name, Decision.source_id)
                .where(Decision.step == TITLE_FILTER_STEP)
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

    plans: list[JudgeTitlePlan] = []
    for c in criteria_rows:
        user = users.get(c.user_id)
        if user is None:
            continue
        for (uid, source_name, source_id) in passed_filter:
            if uid != c.user_id:
                continue
            if (uid, source_name, source_id) in already_judged:
                continue
            job = jobs.get((source_name, source_id))
            if job is None or not job.title:
                continue
            plans.append(
                JudgeTitlePlan(
                    user_id=user.id,
                    user_name=user.name,
                    user_email=user.email,
                    criteria=c.criteria,
                    source_name=source_name,
                    source_id=source_id,
                    title=job.title,
                )
            )
    return plans


def _default_judge(plan: JudgeTitlePlan) -> TitleVerdict:
    prompt = PROMPT_TEMPLATE.format(criteria=plan.criteria, title=plan.title)
    return llm.judge(llm.openai(MODEL), prompt, TitleVerdict)


def execute_judge_title_plan(
    engine: Engine,
    plans: list[JudgeTitlePlan],
    judge: TitleJudge = _default_judge,
) -> Generator[JudgeTitleResult, None, None]:
    insert = dialect_insert(engine)
    for plan in plans:
        verdict = judge(plan)
        result = JudgeTitleResult(
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


def render_judge_title_plan(plans: list[JudgeTitlePlan]) -> str:
    lines: list[str] = []
    by_user: dict[UUID, list[JudgeTitlePlan]] = {}
    for p in plans:
        by_user.setdefault(p.user_id, []).append(p)

    for user_plans in by_user.values():
        head = user_plans[0]
        lines.append(f"\n{head.user_name} ({head.user_email})")
        lines.append(f"  to judge: {len(user_plans)}")
        for p in user_plans:
            lines.append(f"  - {p.source_name}/{p.source_id}  {p.title}")
    return "\n".join(lines)


def plan_judge_title_eval(engine: Engine) -> list[JudgeTitleEvalUser]:
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

    entries_by_user: dict[UUID, list[JudgeTitleEvalEntry]] = {}
    for user_id, source_name, source_id, score, reason, judged_at in decisions:
        job = jobs.get((source_name, source_id))
        if job is None or not job.title:
            continue
        entries_by_user.setdefault(user_id, []).append(
            JudgeTitleEvalEntry(
                source_name=source_name,
                source_id=source_id,
                title=job.title,
                passes=score == 1,
                reason=reason,
                judged_at=judged_at,
            )
        )

    result: list[JudgeTitleEvalUser] = []
    for c in criteria_rows:
        user = users.get(c.user_id)
        if user is None:
            continue
        entries = entries_by_user.get(user.id, [])
        entries.sort(key=lambda e: e.judged_at, reverse=True)
        result.append(
            JudgeTitleEvalUser(
                user_id=user.id,
                user_name=user.name,
                user_email=user.email,
                criteria=c.criteria,
                entries=entries,
            )
        )
    result.sort(key=lambda u: u.user_name)
    return result


def render_judge_title_eval(users: list[JudgeTitleEvalUser]) -> str:
    sections: list[str] = []
    for user in users:
        lines = [
            f"# {user.user_name} ({user.user_email})",
            "",
            user.criteria,
        ]
        if not user.entries:
            lines.append("- _no past judgments_")
        for entry in user.entries:
            verdict = "pass" if entry.passes else f"reject: {entry.reason}"
            lines.append(
                f"- {entry.source_name}/{entry.source_id}  {entry.title} — {verdict}"
            )
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
