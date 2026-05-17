import os

import typer
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool
from sqlmodel import create_engine


def build_engine() -> Engine:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        typer.echo(
            "DATABASE_URL is not set. Set it to a Supabase Postgres URL "
            "using the postgresql+psycopg:// scheme.",
            err=True,
        )
        raise typer.Exit(code=1)
    return create_engine(database_url, poolclass=NullPool)


def dialect_insert(engine: Engine):
    """Return the on-conflict-capable `insert` function for the engine's dialect."""
    if engine.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        from sqlalchemy.dialects.postgresql import insert
    return insert
