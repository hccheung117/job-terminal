import re
from collections import defaultdict

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from models import Keyword


def normalize_group_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "group"


def load_groups(engine: Engine) -> dict[str, list[str]]:
    with Session(engine) as session:
        rows = session.exec(select(Keyword)).all()

    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        raw_group = (row.group or "").strip()
        keyword = (row.keyword or "").strip()
        if not raw_group or not keyword:
            continue
        groups[normalize_group_name(raw_group)].append(keyword)
    return dict(groups)
