import json
import os
import time
from datetime import datetime

try:
    from kafka import KafkaConsumer, KafkaProducer
except ImportError:  # pragma: no cover - optional runtime dependency
    KafkaConsumer = None
    KafkaProducer = None

KAFKA_SERVER = os.environ.get("KAFKA_BROKER", "localhost:9092")
TOPIC = "worldpulse.raw"
KAFKA_AVAILABLE = KafkaConsumer is not None and KafkaProducer is not None


def json_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


producer = None
if KAFKA_AVAILABLE:
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_SERVER,
            value_serializer=lambda v: json.dumps(v, default=json_serializer).encode("utf-8"),
        )
    except Exception:
        producer = None


def send_to_kafka(topic, message, key=None, retries=3, retry_backoff_sec=1.0):
    if producer is None:
        return False

    payload_key = None
    if key is not None:
        payload_key = str(key).encode("utf-8")
    last_error = None
    for attempt in range(retries):
        try:
            future = producer.send(topic, message, key=payload_key)
            future.get(timeout=10)
            producer.flush()
            return True
        except Exception as e:
            last_error = e
            time.sleep(retry_backoff_sec * (attempt + 1))
    print(f"Kafka error on topic {topic}: {last_error}")
    return False


# Consumer
def get_consumer(
    topics=None,
    group_id="worldpulse-group",
    auto_offset_reset="latest",
    enable_auto_commit=True,
    consumer_timeout_ms=1000,
):
    if KafkaConsumer is None:
        raise RuntimeError("Kafka support is not installed in this environment")

    subscribe_topics = topics or [TOPIC]
    if isinstance(subscribe_topics, str):
        subscribe_topics = [subscribe_topics]
    consumer = KafkaConsumer(
        *subscribe_topics,
        bootstrap_servers=KAFKA_SERVER,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset=auto_offset_reset,
        enable_auto_commit=enable_auto_commit,
        group_id=group_id,
        consumer_timeout_ms=consumer_timeout_ms,
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
    )
    return consumer
