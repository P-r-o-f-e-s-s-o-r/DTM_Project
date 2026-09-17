#!/usr/bin/env python3
"""
GridSense - MQTT to MySQL Telemetry Bridge
Subscribes to MQTT telemetry topic, parses incoming feeder sensor payloads,
and persists time-series points to MySQL table `feeder_telemetry`.
Features robust error handling, connection reconnection, and data sanitization.
"""

import os
import sys
import time
import logging
from pathlib import Path
from dotenv import load_dotenv
import pymysql
from pymysql.cursors import DictCursor
import paho.mqtt.client as mqtt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [mqtt_bridge] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("mqtt_to_mysql")

# Load environment configuration
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
else:
    load_dotenv(override=True)

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "gridsense/feeder1/telemetry")
CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "gridsense_mysql_bridge")

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "gridsense")


class MySQLBridge:
    def __init__(self):
        self.db_conn = None
        self.connect_db()

    def connect_db(self):
        """Establish or refresh connection to MySQL database."""
        try:
            self.db_conn = pymysql.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE,
                autocommit=True,
                cursorclass=DictCursor,
                connect_timeout=10
            )
            # Ensure table exists
            with self.db_conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS feeder_telemetry (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        timestamp DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
                        voltage DOUBLE NOT NULL,
                        current DOUBLE NOT NULL,
                        renewable DOUBLE NOT NULL,
                        hosting_index DOUBLE NOT NULL,
                        INDEX idx_timestamp (timestamp)
                    )
                """)
            logger.info("Successfully connected to MySQL database '%s'.", MYSQL_DATABASE)
        except Exception as e:
            logger.error("Failed to connect to MySQL database: %s", e)
            self.db_conn = None

    def insert_telemetry(self, voltage: float, current: float, renewable: float, hosting_index: float) -> bool:
        """Insert a parsed telemetry point into MySQL."""
        if not self.db_conn:
            self.connect_db()
            if not self.db_conn:
                logger.error("Database unavailable. Dropping telemetry record.")
                return False

        query = """
            INSERT INTO feeder_telemetry (voltage, current, renewable, hosting_index)
            VALUES (%s, %s, %s, %s)
        """
        try:
            with self.db_conn.cursor() as cursor:
                cursor.execute(query, (voltage, current, renewable, hosting_index))
            return True
        except pymysql.MySQLError as err:
            logger.warning("MySQL error during insert (%s). Retrying connection...", err)
            try:
                self.connect_db()
                if self.db_conn:
                    with self.db_conn.cursor() as cursor:
                        cursor.execute(query, (voltage, current, renewable, hosting_index))
                    return True
            except Exception as retry_err:
                logger.error("Retry insert failed: %s", retry_err)
        except Exception as ex:
            logger.error("Unexpected error writing to MySQL: %s", ex)
        return False


bridge = MySQLBridge()


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info("Connected to MQTT Broker (%s:%d)", MQTT_HOST, MQTT_PORT)
        client.subscribe(MQTT_TOPIC, qos=0)
        logger.info("Subscribed to topic: '%s'", MQTT_TOPIC)
    else:
        logger.error("Failed to connect to MQTT broker with result code: %s", rc)


def on_message(client, userdata, msg):
    """Handle incoming MQTT messages with error handling for malformed data."""
    try:
        raw_payload = msg.payload.decode("utf-8").strip()
        if not raw_payload:
            logger.warning("Received empty MQTT message payload. Skipping.")
            return

        parts = [p.strip() for p in raw_payload.split(",")]
        if len(parts) != 4:
            logger.warning("Malformed payload (expected 4 CSV values, got %d): '%s'. Skipping.", len(parts), raw_payload)
            return

        voltage = float(parts[0])
        current = float(parts[1])
        renewable = float(parts[2])
        hosting_index = float(parts[3])

        success = bridge.insert_telemetry(voltage, current, renewable, hosting_index)
        if success:
            logger.info("Saved to MySQL -> V: %.2fV | I: %.2fA | Ren: %.2f%% | HI: %.2f", voltage, current, renewable, hosting_index)

    except ValueError as ve:
        logger.warning("Failed to parse numeric telemetry values ('%s'): %s. Skipping.", raw_payload, ve)
    except Exception as e:
        logger.error("Error processing MQTT message: %s", e)


def main():
    logger.info("Starting GridSense MQTT-to-MySQL Bridge...")
    mqtt_client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=CLIENT_ID,
        clean_session=True
    )
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    while True:
        try:
            logger.info("Connecting to MQTT broker at %s:%d...", MQTT_HOST, MQTT_PORT)
            mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            break
        except Exception as e:
            logger.warning("MQTT broker unavailable (%s). Retrying in 3 seconds...", e)
            time.sleep(3)

    try:
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Bridge stopping on user interrupt...")
    finally:
        mqtt_client.disconnect()
        if bridge.db_conn:
            bridge.db_conn.close()
        logger.info("Bridge cleanly shut down.")


if __name__ == "__main__":
    main()
