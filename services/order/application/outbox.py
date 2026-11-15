"""The outbox relay (pattern 7): publishes saved events to the Redis bus, oldest first.

Runs on a background thread in every order replica, once a second. Both replicas read the same
outbox table, so an event can occasionally be published twice; consumers dedupe on event_id
(at-least-once delivery). If Redis is down, events stay in the table, unpublished, and go out
once it is back. Nothing is lost and checkout never waits for the bus.

Demo switch (CHAOS_ENABLED=1 only): disconnect() makes this replica's relay behave as if the bus
were down, so the page can show events piling up and then draining.
"""
import threading
import time
from datetime import datetime, timezone

from shop_common import events

from . import db
from .models import OutboxEvent

BATCH = 50
_bus = {"connected": True}


def set_connected(connected: bool) -> None:
    _bus["connected"] = connected


def is_connected() -> bool:
    return _bus["connected"]


def publish_pending(client, source: str) -> int:
    """Publishes up to BATCH pending events. Returns how many went out."""
    pending = (OutboxEvent.query.filter(OutboxEvent.published_at.is_(None))
               .order_by(OutboxEvent.created_at).limit(BATCH).all())
    sent = 0
    for event in pending:
        try:
            if client is None or not _bus["connected"]:
                raise ConnectionError("event bus unreachable" if client else "no REDIS_URL configured")
            fields = events.to_fields(event.id, event.type, event.payload, source, event.created_at.isoformat())
            client.xadd(events.STREAM, fields, maxlen=10_000, approximate=True)
            event.published_at = datetime.now(timezone.utc)
            event.last_error = None
            sent += 1
        except Exception as exc:  # the bus is down: stop this pass, keep the events for later
            event.attempts += 1
            event.last_error = str(exc)[:200]
            break
    db.session.commit()
    return sent


def start(app, source: str) -> None:
    from shop_common.flask_support import is_serving_process

    if not events.redis_url() or not is_serving_process(app):
        return  # events wait in the table; unit tests, the reloader's watcher and no-Redis land here

    def loop() -> None:
        client = None
        while True:
            time.sleep(1)
            with app.app_context():
                try:
                    client = client or events.connect()
                    publish_pending(client, source)
                except Exception:
                    client = None
                finally:
                    db.session.remove()

    threading.Thread(target=loop, name="outbox-relay", daemon=True).start()
