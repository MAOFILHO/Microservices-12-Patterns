"""The event bus (pattern 7): one Redis Stream, `shop.events`, shared by every service.

- Publishers never write to Redis inside a request. They save the event in their own database's
  outbox table in the same transaction as the business change, and a relay publishes it later
  (see services/order/application/outbox.py). So an event is never lost and never sent for a change
  that was rolled back.
- Consumers read with a consumer group, so each event is handled once per group, and acknowledge
  only after handling it. Unacknowledged events are redelivered after a restart.
- Delivery is at least once. Every handler must be idempotent: handling the same event twice must
  change nothing the second time.

Needs the `redis` package (order and inventory list it). Without REDIS_URL nothing is published or
read, and outbox events simply wait.
"""
import json
import os
import threading
import time
from typing import Callable

STREAM = "shop.events"


def redis_url() -> str | None:
    return os.environ.get("REDIS_URL") or None


def connect():
    """A Redis client with short timeouts, or None when no bus is configured."""
    url = redis_url()
    if not url:
        return None
    import redis

    return redis.Redis.from_url(url, socket_timeout=3, socket_connect_timeout=2, decode_responses=True)


def to_fields(event_id: str, event_type: str, payload: dict, source: str, occurred_at: str) -> dict:
    return {"event_id": event_id, "type": event_type, "payload": json.dumps(payload), "source": source,
            "occurred_at": occurred_at}


def from_fields(fields: dict) -> dict:
    return {**fields, "payload": json.loads(fields.get("payload") or "{}")}


MAX_ATTEMPTS = 5
DEAD_LETTER_STREAM = "shop.events.dead"


class Reader:
    """One consumer in a consumer group. read_once() is one pass; start_consumer() loops it.

    Alternates between new events (">") and this consumer's own unacknowledged ones ("0"), so a
    failing event is retried without holding back the events behind it. After MAX_ATTEMPTS it is
    copied to the dead-letter stream and acknowledged, for a person to look at.
    """

    def __init__(self, group: str, consumer: str, handle: Callable[[dict], None], log=None):
        self.group, self.consumer, self.handle, self.log = group, consumer, handle, log
        self.start_id = "0"  # first pass: our own unacked events from before a restart
        self.failures: dict[str, int] = {}

    def read_once(self, client) -> None:
        start_id = self.start_id
        batches = client.xreadgroup(self.group, self.consumer, {STREAM: start_id}, count=20, block=2000)
        messages = batches[0][1] if batches else []
        for message_id, fields in messages:
            try:
                self.handle(from_fields(fields))
                client.xack(STREAM, self.group, message_id)
                self.failures.pop(message_id, None)
            except Exception as exc:
                attempts = self.failures.get(message_id, 0) + 1
                self.failures[message_id] = attempts
                if self.log:
                    self.log.warning(f"event {message_id} failed (attempt {attempts}): {exc}")
                if attempts >= MAX_ATTEMPTS:
                    client.xadd(DEAD_LETTER_STREAM, {**fields, "group": self.group, "error": str(exc)[:200]})
                    client.xack(STREAM, self.group, message_id)
                    self.failures.pop(message_id, None)
        # Retry failures on the next pass, new events on the one after: neither starves the other.
        self.start_id = "0" if start_id == ">" and self.failures else ">"


def start_consumer(group: str, consumer: str, handle: Callable[[dict], None], log=None) -> threading.Thread | None:
    """Runs a Reader on a background thread. Returns None when no bus is configured."""
    if not redis_url():
        return None
    reader = Reader(group, consumer, handle, log)

    def loop() -> None:
        import redis

        client = None
        while True:
            try:
                if client is None:
                    client = connect()
                    try:
                        client.xgroup_create(STREAM, group, id="0", mkstream=True)
                    except redis.ResponseError as exc:
                        if "BUSYGROUP" not in str(exc):
                            raise
                reader.read_once(client)
                if reader.failures:
                    time.sleep(1)  # do not spin on an event that keeps failing
            except (redis.ConnectionError, redis.TimeoutError, OSError):
                client = None
                time.sleep(2)

    thread = threading.Thread(target=loop, name=f"consumer-{group}", daemon=True)
    thread.start()
    return thread
