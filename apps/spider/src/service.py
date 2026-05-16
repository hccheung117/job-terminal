from collections import defaultdict

from sqlalchemy.pool import NullPool
from sqlmodel import Session, create_engine, select

from models import SpiderKeyword


def load_groups(database_url: str) -> dict[str, list[str]]:
    engine = create_engine(database_url, poolclass=NullPool)
    with Session(engine) as session:
        rows = session.exec(select(SpiderKeyword)).all()

    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        group = (row.group or "").strip()
        keyword = (row.keyword or "").strip()
        if not group or not keyword:
            continue
        groups[group].append(keyword)
    return dict(groups)
