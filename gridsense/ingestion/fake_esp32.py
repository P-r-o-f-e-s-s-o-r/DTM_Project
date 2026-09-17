#!/usr/bin/env python3
"""
GridSense - Simulated ESP32 Distribution Feeder Node
Publishes simulated high-frequency feeder telemetry over MQTT in the exact wire format
used by the physical ESP32 firmware:
  Payload: "voltage,current,renewable,hosting_index"
"""

import os
import sys
import time
import random
import logging
from pathlib import Path
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [fake_esp32] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("fake_esp32")

# Load environment configuration from project root
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "gridsense/feeder1/telemetry")
CLIENT_ID = os.getenv("FAKE_ESP32_CLIENT_ID", "gridsense_fake_esp32")


def compute_hosting_index(voltage: float, current: float, renewable: float) -> float:
    """
    Standardized Hosting Capacity Index (0.0 to 100.0).
    Higher is healthier/more capacity available.
    Lower indicates grid stress, overvoltage, or thermal overload.
    This exact formula is matched in ml/generate_synthetic_data.py and firmware/main.cpp.
    """
    # 1. Voltage deviation penalty from nominal 230V (standard: 230V +/- 6%)
    v_dev = abs(voltage - 230.0)
    v_penalty = (v_dev / 20.0) * 40.0  # up to 40 pts penalty at 210V or 250V

    # 2. Thermal loading penalty (nominal <= 35A, rated feeder capacity 60A)
    c_penalty = max(0.0, (current - 35.0) / 25.0) * 35.0  # up to 35 pts penalty at 60A

    # 3. Renewable stress & reverse power flow penalty
    r_penalty = 0.0
    if renewable > 60.0 and voltage > 235.0:
        # High renewable generation during light load / high voltage
        r_penalty = ((renewable - 60.0) / 20.0) * ((voltage - 235.0) / 10.0) * 25.0
    elif current > 45.0 and renewable < 30.0:
        # High grid draw with minimal local generation
        r_penalty = ((30.0 - renewable) / 20.0) * 15.0

    raw_hi = 100.0 - (v_penalty + c_penalty + r_penalty)
    return round(max(0.0, min(100.0, raw_hi)), 2)


def generate_telemetry():
    """Generate realistic feeder readings with realistic drift."""
    # Voltage: 210 - 245V centered around 230V
    voltage = round(random.gauss(230.0, 4.5), 2)
    voltage = max(210.0, min(245.0, voltage))

    # Current: 10 - 60A with occasional peak loads
    current = round(random.uniform(12.0, 52.0), 2)
    if random.random() < 0.12:  # occasional high-load surge
        current = round(random.uniform(52.0, 59.5), 2)

    # Renewable: 20 - 80%
    renewable = round(random.uniform(20.0, 80.0), 2)

    hosting_index = compute_hosting_index(voltage, current, renewable)
    return voltage, current, renewable, hosting_index


def main():
    logger.info("Initializing simulated ESP32 node...")
    logger.info(f"Target Broker: {MQTT_HOST}:{MQTT_PORT}")
    logger.info(f"Publish Topic: {MQTT_TOPIC}")

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=CLIENT_ID,
        clean_session=True
    )

    connected = False

    def on_connect(c, userdata, flags, rc, properties=None):
        nonlocal connected
        if rc == 0:
            connected = True
            logger.info("Successfully connected to MQTT broker.")
        else:
            logger.error(f"Failed to connect to broker, return code: {rc}")

    client.on_connect = on_connect

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        logger.error(f"Error connecting to MQTT broker: {e}")
        sys.exit(1)

    # Wait briefly for connection
    for _ in range(10):
        if connected:
            break
        time.sleep(0.2)

    logger.info("Starting telemetry transmission loop (interval: 2.0s)...")
    try:
        while True:
            v, c, r, hi = generate_telemetry()
            # Exact wire format: "voltage,current,renewable,hosting_index"
            payload = f"{v:.2f},{c:.2f},{r:.2f},{hi:.2f}"
            res = client.publish(MQTT_TOPIC, payload, qos=0)
            if res.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Published: {payload} (V={v}V, I={c}A, Ren={r}%, HI={hi})")
            else:
                logger.warning(f"Failed to publish message (rc={res.rc})")

            time.sleep(2.0)
    except KeyboardInterrupt:
        logger.info("Simulated ESP32 stopped by user.")
    finally:
        client.loop_stop()
        client.disconnect()
        logger.info("Disconnected from MQTT broker.")


if __name__ == "__main__":
    main()
