"""
E-commerce event producer: generates realistic e-commerce events with product metadata,
pricing, and session tracking. Publishes to Kafka.
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
SESSION_TIMEOUT = 1800  # 30 minutes in seconds

# E-commerce event types (view replaces click)
EVENT_TYPES = ["login", "view", "add_to_cart", "purchase", "logout"]
EVENT_WEIGHTS = [0.05, 0.70, 0.15, 0.02, 0.08]  # Realistic: 2% purchases for ~2-4% conversion rate

SOURCES = ["web", "mobile"]

# Product categories with pricing and popularity
CATEGORIES = {
    "Electronics": {"code": "ELEC", "price_range": (49.99, 999.99), "popular": 0.25},
    "Fashion": {"code": "FASH", "price_range": (19.99, 299.99), "popular": 0.20},
    "Home": {"code": "HOME", "price_range": (29.99, 499.99), "popular": 0.15},
    "Books": {"code": "BOOK", "price_range": (9.99, 59.99), "popular": 0.10},
    "Sports": {"code": "SPRT", "price_range": (24.99, 399.99), "popular": 0.10},
    "Beauty": {"code": "BEAU", "price_range": (14.99, 149.99), "popular": 0.10},
    "Toys": {"code": "TOYS", "price_range": (9.99, 199.99), "popular": 0.05},
    "Food": {"code": "FOOD", "price_range": (4.99, 99.99), "popular": 0.05},
}

# Global caches
_start_time = time.time()
_active_users_cache = set()  # Track recently active users
PRODUCT_CACHE = {}  # Cache of product_id -> {category, price}
SESSION_CACHE = {}  # user_id -> {session_id, last_activity, cart_items}


def get_current_user_pool() -> int:
    """Calculate current user pool size based on time elapsed."""
    hours_elapsed = (time.time() - _start_time) / 3600
    growth = int(hours_elapsed * USER_GROWTH_RATE)
    return BASE_USERS + growth


def get_or_create_session(user_id: int) -> dict:
    """Get existing session or create new one for user."""
    current_time = time.time()

    if user_id in SESSION_CACHE:
        session = SESSION_CACHE[user_id]
        # Check if session expired
        if current_time - session['last_activity'] > SESSION_TIMEOUT:
            # Session expired, create new one
            session = create_new_session(user_id)
        else:
            session['last_activity'] = current_time
    else:
        session = create_new_session(user_id)

    SESSION_CACHE[user_id] = session
    return session


def create_new_session(user_id: int) -> dict:
    """Create a new session for a user."""
    return {
        'session_id': str(uuid.uuid4()),
        'last_activity': time.time(),
        'cart_items': []
    }


def end_session(user_id: int):
    """End a user's session (on logout)."""
    if user_id in SESSION_CACHE:
        del SESSION_CACHE[user_id]


def generate_product(category: str) -> dict:
    """Generate or retrieve a product."""
    cat_info = CATEGORIES[category]

    # 70% chance to reuse existing product, 30% create new
    if random.random() < 0.7 and len(PRODUCT_CACHE) > 100:
        product_id = random.choice(list(PRODUCT_CACHE.keys()))
        return PRODUCT_CACHE[product_id]

    # Create new product
    product_id = f"PROD-{cat_info['code']}-{random.randint(10000, 99999)}"
    price = round(random.uniform(*cat_info['price_range']), 2)
    product = {
        'product_id': product_id,
        'category': category,
        'price': price
    }

    PRODUCT_CACHE[product_id] = product
    return product


def create_event() -> dict:
    """Create a contextual e-commerce event."""
    current_pool = get_current_user_pool()

    # 80% of events from existing active users, 20% from new/returning users
    if random.random() < 0.8 and _active_users_cache:
        user_id = random.choice(list(_active_users_cache))
    else:
        user_id = random.randint(1, current_pool)

    # Keep cache size manageable
    _active_users_cache.add(user_id)
    if len(_active_users_cache) > 200:
        _active_users_cache.pop()

    # Get or create session
    session = get_or_create_session(user_id)

    # Select event type with weights
    event_type = random.choices(EVENT_TYPES, weights=EVENT_WEIGHTS, k=1)[0]

    # Base event structure
    event = {
        "event_id": str(uuid.uuid4()),
        "user_id": user_id,
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": random.choice(SOURCES),
        "session_id": session['session_id'],
    }

    # Apply contextual rules based on event type
    if event_type == "login":
        event["page"] = "/home"
        event["price"] = None
        event["category"] = None
        event["product_id"] = None
        # Clear cart on new session
        session['cart_items'] = []

    elif event_type == "logout":
        event["page"] = random.choice(["/home", "/profile", "/settings"])
        event["price"] = None
        event["category"] = None
        event["product_id"] = None
        end_session(user_id)

    elif event_type == "view":
        # 60% product pages, 40% other pages
        if random.random() < 0.6:
            event["page"] = random.choice(["/products", "/products/detail"])
            # Select category by popularity
            category = random.choices(
                list(CATEGORIES.keys()),
                weights=[c['popular'] for c in CATEGORIES.values()],
                k=1
            )[0]
            product = generate_product(category)
            event["product_id"] = product['product_id']
            event["category"] = product['category']
            event["price"] = product['price']
        else:
            event["page"] = random.choice(["/home", "/search", "/about", "/help", "/profile"])
            event["price"] = None
            event["category"] = None
            event["product_id"] = None

    elif event_type == "add_to_cart":
        # Add to cart only on product pages
        event["page"] = random.choice(["/products/detail", "/cart"])
        category = random.choices(
            list(CATEGORIES.keys()),
            weights=[c['popular'] for c in CATEGORIES.values()],
            k=1
        )[0]
        product = generate_product(category)
        event["product_id"] = product['product_id']
        event["category"] = product['category']
        event["price"] = product['price']

        # Add to session cart (max 10 items)
        if len(session['cart_items']) < 10:
            session['cart_items'].append(product)

    elif event_type == "purchase":
        # Purchases ONLY happen on /checkout
        event["page"] = "/checkout"

        # 80% chance to purchase from cart, 20% impulse buy
        if session['cart_items'] and random.random() < 0.8:
            product = random.choice(session['cart_items'])
            session['cart_items'].remove(product)
        else:
            # Impulse buy - random product
            category = random.choices(
                list(CATEGORIES.keys()),
                weights=[c['popular'] for c in CATEGORIES.values()],
                k=1
            )[0]
            product = generate_product(category)

        event["product_id"] = product['product_id']
        event["category"] = product['category']
        event["price"] = product['price']

    return event


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
            print(f"✓ Connected to Kafka at {KAFKA_BOOTSTRAP}")
            return producer
        except NoBrokersAvailable:
            print(f"Kafka not ready (attempt {attempt}/{max_retries}), retrying in {delay}s...")
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to Kafka after {max_retries} attempts")


def main():
    producer = connect_with_retry()
    interval = 1.0 / EVENTS_PER_SECOND
    total_sent = 0

    print(f"✓ E-commerce event producer started")
    print(f"  - Events/sec: {EVENTS_PER_SECOND}")
    print(f"  - Topic: '{KAFKA_TOPIC}'")
    print(f"  - Users: {BASE_USERS} (growing at {USER_GROWTH_RATE}/hour)")
    print(f"  - Categories: {len(CATEGORIES)}")
    print(f"  - Event types: {', '.join(EVENT_TYPES)}")

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
                products = len(PRODUCT_CACHE)
                sessions = len(SESSION_CACHE)
                print(f"Sent {total_sent} events | Users: {current_pool} | Active: {active_count} | Products: {products} | Sessions: {sessions}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n✓ Shutting down. Total events sent: {total_sent}")
    finally:
        producer.flush()
        producer.close()


if __name__ == "__main__":
    main()
