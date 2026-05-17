from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from sqlalchemy.sql import text
from sqlmodel import Session

from job_terminal_models import Job

SOURCE_NAME = "linkedin"


def upsert_jobs(engine: Engine, records: list[dict]) -> int:
    if not records:
        return 0

    merge_groups = text(
        "COALESCE("
        "(SELECT ARRAY_AGG(DISTINCT g) "
        "FROM UNNEST(jobs.groups || EXCLUDED.groups) AS merged(g) "
        "WHERE g <> ''), '{}')"
    )

    stmt = insert(Job).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_name", "source_id"],
        set_={
            "groups": merge_groups,
            "location": stmt.excluded.location,
            "title": stmt.excluded.title,
            "jd": stmt.excluded.jd,
            "url": stmt.excluded.url,
            "published_at": stmt.excluded.published_at,
        },
    )

    with Session(engine) as session:
        session.exec(stmt)
        session.commit()

    return len(records)


def update_jd(engine: Engine, source_id: str, jd: str) -> None:
    sql = text(
        "UPDATE jobs SET jd = :jd "
        "WHERE source_name = :source_name AND source_id = :source_id"
    )
    with Session(engine) as session:
        session.exec(sql.bindparams(
            jd=jd,
            source_name=SOURCE_NAME,
            source_id=source_id,
        ))
        session.commit()
