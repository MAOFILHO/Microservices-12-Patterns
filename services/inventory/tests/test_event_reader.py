"""The bus reader in shop_common.events, driven with a fake Redis (pattern 7).

One event that keeps failing must not stop the events behind it, and must not be retried forever.
"""
from shop_common import events


class FakeRedis:
    """Just enough of a consumer group: new messages, a pending list, acks, a dead-letter stream."""

    def __init__(self, messages):
        self.new = list(messages)
        self.pending = {}
        self.acked = []
        self.dead = []

    def xreadgroup(self, group, consumer, streams, count, block):
        start = streams[events.STREAM]
        if start == "0":
            batch = list(self.pending.items())
        else:
            batch, self.new = self.new[:count], self.new[count:]
            self.pending.update(batch)
        return [(events.STREAM, batch)] if batch else []

    def xack(self, stream, group, message_id):
        self.acked.append(message_id)
        self.pending.pop(message_id, None)

    def xadd(self, stream, fields, **kwargs):
        assert stream == events.DEAD_LETTER_STREAM
        self.dead.append(fields["event_id"])


def _event(n, event_type="OrderConfirmed"):
    return f"{n}-0", events.to_fields(f"evt-{n}", event_type, {}, "test", "now")


def test_a_failing_event_does_not_block_the_events_behind_it():
    redis = FakeRedis([_event(1, "Poison")])
    handled = []

    def handle(event):
        if event["type"] == "Poison":
            raise ValueError("cannot handle")
        handled.append(event["event_id"])

    reader = events.Reader("inventory", "inventory-1", handle)
    reader.read_once(redis)                 # the poison event fails
    redis.new.append(_event(2))             # a good event arrives after it
    for _ in range(4):
        reader.read_once(redis)
    assert handled == ["evt-2"]


def test_an_event_that_keeps_failing_goes_to_the_dead_letter_stream():
    redis = FakeRedis([_event(1, "Poison")])

    def handle(event):
        raise ValueError("cannot handle")

    reader = events.Reader("inventory", "inventory-1", handle)
    for _ in range(2 * events.MAX_ATTEMPTS):
        reader.read_once(redis)
    assert redis.dead == ["evt-1"]
    assert redis.acked == ["1-0"]
    assert redis.pending == {}
