from kafka import KafkaProducer, KafkaConsumer
import json

KAFKA_SERVER = "localhost:9092"
TOPIC = "worldpulse.raw"

# Producer
producer = KafkaProducer(
    bootstrap_servers=KAFKA_SERVER,
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

def send_to_kafka(data):
    producer.send(TOPIC, data)
    producer.flush()

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
