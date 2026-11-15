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


def start_consumer(group: str, consumer: str, handle: Callable[[dict], None], log=None) -> threading.Thread | None:
    """Reads the stream as `consumer` in `group` on a background thread and acks each handled event.

    handle() gets the decoded event. If it raises, the event is not acked and is retried on the
    next pass. Returns None when no bus is configured.
    """
    if not redis_url():
        return None

    def loop() -> None:
        import redis

        client, start_id = None, "0"  # "0" first: our own unacked events from before a restart
        while True:
            try:
                if client is None:
                    client = connect()
                    try:
                        client.xgroup_create(STREAM, group, id="0", mkstream=True)
                    except redis.ResponseError as exc:
                        if "BUSYGROUP" not in str(exc):
                            raise
                batches = client.xreadgroup(group, consumer, {STREAM: start_id}, count=20, block=2000)
                messages = batches[0][1] if batches else []
                if start_id == "0" and not messages:
                    start_id = ">"  # backlog done, now only new events
                for message_id, fields in messages:
                    try:
                        handle(from_fields(fields))
                        client.xack(STREAM, group, message_id)
                    except Exception as exc:  # leave it unacked; it is retried from "0" next pass
                        if log:
                            log.warning(f"event {message_id} failed: {exc}")
                        start_id = "0"
                        time.sleep(1)  # do not spin on an event that keeps failing
            except (redis.ConnectionError, redis.TimeoutError, OSError):
                client = None
                time.sleep(2)

    thread = threading.Thread(target=loop, name=f"consumer-{group}", daemon=True)
    thread.start()
    return thread
