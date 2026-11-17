"""Creating a service's tables at startup, safely when several replicas start at once."""
from sqlalchemy.exc import OperationalError


def create_tables(db) -> None:
    """db.create_all(), tolerating another replica creating the same table at the same moment.

    create_all() checks which tables exist, then creates the missing ones. Two replicas sharing a
    database can both pass the check, and the slower one then fails with "already exists". On that
    error only, run it once more: the check now sees the table and skips it.
    """
    try:
        db.create_all()
    except OperationalError as exc:
        if "already exists" not in str(exc):
            raise
        db.session.rollback()
        db.create_all()


def add_missing_columns(db) -> None:
    """Adds model columns that an existing table lacks, so a database made by an older version
    keeps its rows (there are no Alembic revisions). Only for new nullable columns: a unique one
    gets a unique index, which allows many NULLs on SQLite and MySQL. Safe when two processes
    start at once: a column or index the other one just added is skipped.
    """
    from sqlalchemy import inspect

    inspector = inspect(db.engine)
    quote = db.engine.dialect.identifier_preparer.quote
    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        present = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present or not column.nullable:
                continue
            kind = column.type.compile(dialect=db.engine.dialect)
            _run_once(db, f"ALTER TABLE {quote(table.name)} ADD COLUMN {quote(column.name)} {kind}")
            if column.unique:
                index = quote(f"uq_{table.name}_{column.name}")
                _run_once(db, f"CREATE UNIQUE INDEX {index} ON {quote(table.name)} ({quote(column.name)})")


def _run_once(db, statement: str) -> None:
    """Runs one schema change, skipping it if another process already made it."""
    from sqlalchemy import text

    try:
        db.session.execute(text(statement))
        db.session.commit()
    except OperationalError as exc:
        db.session.rollback()
        if "duplicate" not in str(exc).lower() and "already exists" not in str(exc).lower():
            raise
