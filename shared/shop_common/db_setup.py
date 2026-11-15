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
