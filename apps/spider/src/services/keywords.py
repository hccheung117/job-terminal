from collections import defaultdict

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from models import Keyword


def load_groups(engine: Engine) -> dict[str, list[str]]:
    with Session(engine) as session:
        rows = session.exec(select(Keyword)).all()

    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        group = (row.group or "").strip()
        keyword = (row.keyword or "").strip()
        if not group or not keyword:
            continue
        groups[group].append(keyword)
    return dict(groups)
