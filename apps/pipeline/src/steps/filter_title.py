import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from job_terminal_models import Decision, Job
from models import Stopword, User

STEP = "title_filter"


@dataclass
class FilterTitlePlan:
    user_id: UUID
    user_name: str
    user_email: str
    source_name: str
    source_id: str
    title: str
    matched_keyword: str
    scope_type: str
    scope_id: str


def _compile_pattern(keywords: list[str]) -> re.Pattern[str] | None:
    parts = [re.escape(k) for k in keywords if k]
    if not parts:
        return None
    return re.compile(rf"\b(?:{'|'.join(parts)})\b", re.IGNORECASE)


def plan_filter_title(engine: Engine) -> list[FilterTitlePlan]:
    plans: list[FilterTitlePlan] = []

    with Session(engine) as session:
        stopwords = session.exec(select(Stopword)).all()
        users = session.exec(select(User)).all()
        jobs = session.exec(select(Job)).all()
        decided = set(
            session.exec(
                select(
                    Decision.user_id,
                    Decision.source_name,
                    Decision.source_id,
                ).where(Decision.step == STEP)
            ).all()
        )

    group_keywords: dict[str, list[str]] = {}
    user_keywords: dict[UUID, list[str]] = {}
    for sw in stopwords:
        if sw.scope_type == "group":
            group_keywords.setdefault(sw.scope_id, []).append(sw.keyword)
        elif sw.scope_type == "user":
            try:
                uid = UUID(sw.scope_id)
            except ValueError:
                print(
                    f"warning: stopword scope_id {sw.scope_id!r} is not a UUID; skipping",
                    file=sys.stderr,
                )
                continue
            user_keywords.setdefault(uid, []).append(sw.keyword)

    group_patterns = {g: p for g, kws in group_keywords.items() if (p := _compile_pattern(kws))}
    user_patterns = {u: p for u, kws in user_keywords.items() if (p := _compile_pattern(kws))}

    for job in jobs:
        title = job.title
        if not title:
            continue

        # Group pass: a match rejects the job for every user.
        group_hit: tuple[str, str] | None = None
        for group in job.groups or []:
            pattern = group_patterns.get(group)
            if pattern and (m := pattern.search(title)):
                group_hit = (m.group(0).lower(), group)
                break

        if group_hit:
            kw, group = group_hit
            for user in users:
                if (user.id, job.source_name, job.source_id) in decided:
                    continue
                plans.append(
                    FilterTitlePlan(
                        user_id=user.id,
                        user_name=user.name,
                        user_email=user.email,
                        source_name=job.source_name,
                        source_id=job.source_id,
                        title=title,
                        matched_keyword=kw,
                        scope_type="group",
                        scope_id=group,
                    )
                )
            continue

        # User pass: a match rejects the job only for that user.
        for user in users:
            if (user.id, job.source_name, job.source_id) in decided:
                continue
            pattern = user_patterns.get(user.id)
            if pattern and (m := pattern.search(title)):
                plans.append(
                    FilterTitlePlan(
                        user_id=user.id,
                        user_name=user.name,
                        user_email=user.email,
                        source_name=job.source_name,
                        source_id=job.source_id,
                        title=title,
                        matched_keyword=m.group(0).lower(),
                        scope_type="user",
                        scope_id=str(user.id),
                    )
                )

    return plans


def execute_filter_title_plan(engine: Engine, plans: list[FilterTitlePlan]) -> int:
    if not plans:
        return 0

    judged_at = datetime.now(timezone.utc)
    rows = [
        {
            "user_id": p.user_id,
            "source_name": p.source_name,
            "source_id": p.source_id,
            "step": STEP,
            "score": 0,
            "reason": f"stopword: {p.matched_keyword}",
            "judged_at": judged_at,
        }
        for p in plans
    ]

    stmt = insert(Decision).values(rows).on_conflict_do_nothing(
        index_elements=["user_id", "source_name", "source_id", "step"],
    )

    with Session(engine) as session:
        session.exec(stmt)
        session.commit()

    return len(rows)


def render_filter_title_plan(plans: list[FilterTitlePlan]) -> None:
    by_user: dict[UUID, list[FilterTitlePlan]] = {}
    for p in plans:
        by_user.setdefault(p.user_id, []).append(p)

    for user_plans in by_user.values():
        head = user_plans[0]
        print(f"\n{head.user_name} ({head.user_email})", file=sys.stderr)
        print(f"  rejections: {len(user_plans)}", file=sys.stderr)
        for p in user_plans:
            print(
                f"  - {p.source_name}/{p.source_id}  "
                f"[{p.scope_type}:{p.scope_id} -> {p.matched_keyword!r}]  "
                f"{p.title}",
                file=sys.stderr,
            )
