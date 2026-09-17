#!/usr/bin/env bash
# ============================================================================
# GridSense - Launch Full Simulated Pipeline (Bash)
# Starts: Mosquitto -> Bridge -> Fake ESP32 -> Risk API -> Backend API -> Frontend
# ============================================================================

set -e
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "=========================================================="
echo "   Starting GridSense Autonomous Feeder Monitoring Stack  "
echo "=========================================================="

# 1. Start Mosquitto if not running
if ! pgrep -x "mosquitto" > /dev/null; then
    echo "[1/6] Starting Mosquitto broker (port 1883)..."
    mosquitto -c mosquitto.conf -d || true
else
    echo "[1/6] Mosquitto broker is already running."
fi
sleep 1

# 2. Start Bridge
echo "[2/6] Starting MQTT -> MySQL Telemetry Bridge..."
python3 ingestion/mqtt_to_mysql.py &
BRIDGE_PID=$!
sleep 2

# 3. Start Risk API
echo "[3/6] Starting AI Risk Prediction Microservice (Port 8001)..."
python3 -m uvicorn services.risk_api.main:app --host 127.0.0.1 --port 8001 &
RISK_PID=$!
sleep 2

# 4. Start Backend API
echo "[4/6] Starting Backend Orchestration API (Port 8000)..."
python3 -m uvicorn services.backend_api.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
sleep 2

# 5. Start Simulated ESP32
echo "[5/6] Starting Simulated ESP32 Feeder Publisher..."
python3 ingestion/fake_esp32.py &
SIM_PID=$!
sleep 2

cleanup() {
    echo -e "\nShutting down GridSense services..."
    kill "$SIM_PID" "$BACKEND_PID" "$RISK_PID" "$BRIDGE_PID" 2>/dev/null || true
    echo "Done."
}
trap cleanup EXIT INT TERM

# 6. Start React Frontend
echo "[6/6] Starting Frontend Dashboard at http://localhost:5173..."
npm --prefix frontend run dev
