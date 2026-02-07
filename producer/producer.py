"""
Event producer: generates realistic user-event JSON and publishes to Kafka.
Configurable via environment variables.
"""

import json
import os
import random
import time
import uuid
from datetime import datetime, timezone

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

# --------------- Configuration ---------------
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "user-events")
EVENTS_PER_SECOND = int(os.getenv("EVENTS_PER_SECOND", "5"))
BASE_USERS = int(os.getenv("NUM_USERS", "100"))
USER_GROWTH_RATE = int(os.getenv("USER_GROWTH_RATE", "10"))  # New users per hour

EVENT_TYPES = ["login", "click", "purchase", "logout"]
EVENT_WEIGHTS = [0.20, 0.50, 0.15, 0.15]  # click-heavy distribution
SOURCES = ["web", "mobile"]
PAGES = [
    "/home", "/products", "/products/detail", "/cart",
    "/checkout", "/profile", "/settings", "/search",
    "/about", "/help",
]

# Track growing user base
_start_time = time.time()
_active_users_cache = set()  # Track recently active users


def get_current_user_pool() -> int:
    """Calculate current user pool size based on time elapsed."""
    hours_elapsed = (time.time() - _start_time) / 3600
    growth = int(hours_elapsed * USER_GROWTH_RATE)
    return BASE_USERS + growth


def create_event() -> dict:
    current_pool = get_current_user_pool()
    # 80% of events from existing active users, 20% from new/returning users
    if random.random() < 0.8 and _active_users_cache:
        user_id = random.choice(list(_active_users_cache))
    else:
        user_id = random.randint(1, current_pool)

    # Keep cache size manageable (last ~200 active users)
    _active_users_cache.add(user_id)
    if len(_active_users_cache) > 200:
        _active_users_cache.pop()

    return {
        "event_id": str(uuid.uuid4()),
        "user_id": user_id,
        "event_type": random.choices(EVENT_TYPES, weights=EVENT_WEIGHTS, k=1)[0],
        "page": random.choice(PAGES),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": random.choice(SOURCES),
    }


def connect_with_retry(max_retries: int = 30, delay: int = 5) -> KafkaProducer:
    for attempt in range(1, max_retries + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                retries=3,
            )
            print(f"Connected to Kafka at {KAFKA_BOOTSTRAP}")
            return producer
        except NoBrokersAvailable:
            print(f"Kafka not ready (attempt {attempt}/{max_retries}), retrying in {delay}s...")
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to Kafka after {max_retries} attempts")


def main():
    producer = connect_with_retry()
    interval = 1.0 / EVENTS_PER_SECOND
    total_sent = 0

    print(f"Producing ~{EVENTS_PER_SECOND} events/sec to topic '{KAFKA_TOPIC}'")
    print(f"Starting with {BASE_USERS} users, growing at {USER_GROWTH_RATE}/hour")

    try:
        while True:
            event = create_event()
            producer.send(
                KAFKA_TOPIC,
                key=event["event_type"],
                value=event,
            )
            total_sent += 1
            if total_sent % 50 == 0:
                current_pool = get_current_user_pool()
                active_count = len(_active_users_cache)
                print(f"Sent {total_sent} events | User pool: {current_pool} | Active: {active_count} | Latest: {event['event_type']} user={event['user_id']}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\nShutting down. Total events sent: {total_sent}")
    finally:
        producer.flush()
        producer.close()


if __name__ == "__main__":
    main()
