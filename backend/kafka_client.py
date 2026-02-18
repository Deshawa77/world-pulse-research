from kafka import KafkaProducer, KafkaConsumer
import json
from datetime import datetime

KAFKA_SERVER = "localhost:9092"
TOPIC = "worldpulse.raw"

def json_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)

producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER,
    value_serializer=lambda v: json.dumps(v, default=json_serializer).encode("utf-8")
)

def send_to_kafka(topic, message):
    try:
        producer.send(topic, message)
        producer.flush()
    except Exception as e:
        print(f"Kafka error: {e}")

# Consumer
def get_consumer():
    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=KAFKA_SERVER,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="latest",
        group_id="worldpulse-group"
    )
    return consumer
