import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, Field as PydField
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from db import dialect_insert
from job_terminal_models import Decision, Job
from models import Criteria, User
from paths import PROMPTS_DIR

STEP = "title_judge"
TITLE_FILTER_STEP = "title_filter"
MODEL_NAME = "gemini-3.1-flash-lite-preview"

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


class TitleVerdict(BaseModel):
    passes: bool = PydField(description="True if the job title passes the user's criteria.")
    reason: str = PydField(description="Concise reason for the decision.")


class TitleJudge(Protocol):
    def __call__(self, plan: JudgeTitlePlan) -> TitleVerdict: ...


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


def _build_default_judge() -> TitleJudge:
    from langchain_google_genai import ChatGoogleGenerativeAI

    model = ChatGoogleGenerativeAI(model=MODEL_NAME).with_structured_output(TitleVerdict)

    def judge(plan: JudgeTitlePlan) -> TitleVerdict:
        prompt = PROMPT_TEMPLATE.format(
            criteria=plan.criteria,
            source_name=plan.source_name,
            source_id=plan.source_id,
            title=plan.title,
        )
        result = model.invoke(prompt)
        if not isinstance(result, TitleVerdict):
            raise RuntimeError(f"Unexpected Gemini structured output: {result!r}")
        return result

    return judge


def execute_judge_title_plan(
    engine: Engine,
    plans: list[JudgeTitlePlan],
    judge: TitleJudge | None = None,
) -> int:
    if not plans:
        return 0

    judge_fn: TitleJudge = judge if judge is not None else _build_default_judge()

    results: list[JudgeTitleResult] = []
    for plan in plans:
        verdict = judge_fn(plan)
        results.append(JudgeTitleResult(plan=plan, passes=verdict.passes, reason=verdict.reason))

    judged_at = datetime.now(timezone.utc)
    rows = [
        {
            "user_id": r.plan.user_id,
            "source_name": r.plan.source_name,
            "source_id": r.plan.source_id,
            "step": STEP,
            "score": 1 if r.passes else 0,
            "reason": None if r.passes else r.reason,
            "judged_at": judged_at,
        }
        for r in results
    ]

    insert = dialect_insert(engine)
    stmt = insert(Decision).values(rows).on_conflict_do_nothing(
        index_elements=["user_id", "source_name", "source_id", "step"],
    )

    with Session(engine) as session:
        session.exec(stmt)
        session.commit()

    return len(rows)


def render_judge_title_plan(plans: list[JudgeTitlePlan]) -> None:
    by_user: dict[UUID, list[JudgeTitlePlan]] = {}
    for p in plans:
        by_user.setdefault(p.user_id, []).append(p)

    for user_plans in by_user.values():
        head = user_plans[0]
        print(f"\n{head.user_name} ({head.user_email})", file=sys.stderr)
        print(f"  to judge: {len(user_plans)}", file=sys.stderr)
        for p in user_plans:
            print(f"  - {p.source_name}/{p.source_id}  {p.title}", file=sys.stderr)
