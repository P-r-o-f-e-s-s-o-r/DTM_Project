# GridSense: AI-Powered Distribution-Feeder Monitoring Platform

GridSense is an autonomous distribution-feeder intelligence system designed to monitor high-frequency electrical telemetry (RMS Voltage, RMS Current, Renewable Penetration, and Hosting Capacity Index), persist time-series data to MySQL, evaluate grid operating risks using an advanced AI Engine (OpenRouter LLM + local Random Forest fallback), and stream real-time insights to an interactive React dashboard via WebSockets.

---

## 1. System Architecture

```
[ ESP32 Hardware Node / fake_esp32.py ]
               │
               ▼ MQTT Publish ("voltage,current,renewable,hosting_index")
[ Mosquitto MQTT Broker :1883 ]
               │
               ▼ MQTT Subscribe
[ Ingestion Bridge: mqtt_to_mysql.py ]
               │
               ▼ INSERT SQL
[ MySQL 8.0 Database: gridsense.feeder_telemetry ]
               ▲
               │ SELECT Latest & Trends
[ Backend API (FastAPI) :8000 ] ◄── POST /predict ──► [ Risk API (FastAPI) :8001 ]
               │                                      (OpenRouter LLM + Local RF)
               ▼ WebSocket (/ws/live, 2s interval)
[ React Dashboard (Vite + Tailwind + Recharts) :5173 ]
```

---

## 2. Technology Stack

| Component | Technology | Role |
|---|---|---|
| **MQTT Broker** | Eclipse Mosquitto (Native Windows/Linux) | Ingests sensor payloads at port `1883` |
| **Telemetry Storage** | MySQL 8.0 (`feeder_telemetry` table) | Time-series data persistence with sub-second indexing |
| **AI Risk Engine** | OpenRouter LLM (`openai/gpt-4o-mini`) + Local Scikit-Learn Random Forest | Real-time feeder risk classification (`safe`/`caution`/`critical`) with engineering diagnosis |
| **Microservice Layer** | FastAPI + Uvicorn + Pydantic + HTTPX | Microservice API (`/predict`, `/health`) |
| **Orchestration Layer**| FastAPI + WebSockets + PyMySQL | Stitches database, AI risk engine, and streams telemetry |
| **Frontend Dashboard** | React 19 (Vite) + Tailwind CSS + Recharts + Lucide | Control-center dashboard with live charts, gauges & alerts |
| **Sensor Simulator** | Python `paho-mqtt` | Accurate simulated stand-in for ESP32 hardware node |
| **Firmware Code** | C++ (Arduino Framework / ESP32 Core) | Production-ready firmware for integration day |

---

## 3. Prerequisites & Native Setup (No Docker)

### 3.1 Mosquitto MQTT Broker
- **Installed location**: `%USERPROFILE%\tools\mosquitto\mosquitto.exe` (or `C:\Program Files\mosquitto`).
- **Configuration**: Uses `gridsense/mosquitto.conf` (configured with `listener 1883` and `allow_anonymous true`).
- **To run manually**:
  ```powershell
  & "$env:USERPROFILE\tools\mosquitto\mosquitto.exe" -c "gridsense\mosquitto.conf" -v
  ```

### 3.2 MySQL 8.0 Server
- **Service Name**: `MySQL80` (running natively on Windows port `3306`).
- **Database & Table Setup**:
  The ingestion bridge automatically creates the table `gridsense.feeder_telemetry` on startup. To verify or create manually:
  ```sql
  CREATE DATABASE IF NOT EXISTS gridsense;
  USE gridsense;
  CREATE TABLE IF NOT EXISTS feeder_telemetry (
      id BIGINT AUTO_INCREMENT PRIMARY KEY,
      timestamp DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
      voltage DOUBLE NOT NULL,
      current DOUBLE NOT NULL,
      renewable DOUBLE NOT NULL,
      hosting_index DOUBLE NOT NULL,
      INDEX idx_timestamp (timestamp)
  );
  ```

### 3.3 Python Environment
- Python 3.11+ or 3.13+ installed.
- Required packages:
  ```powershell
  pip install -r ingestion/requirements.txt
  pip install -r ml/requirements.txt
  pip install -r services/risk_api/requirements.txt
  pip install -r services/backend_api/requirements.txt
  ```

### 3.4 Node.js Environment
- Node 18+ and npm installed.
- In `frontend/`:
  ```bash
  npm install
  ```

---

## 4. How to Run Everything Today (Simulated Mode)

### Option A: One-Click Launch (Recommended)
Open a PowerShell terminal in the `gridsense/` directory and execute:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_all.ps1
```
*(On Linux/macOS, execute: `./scripts/run_all.sh`)*

This script automatically:
1. Starts Mosquitto MQTT broker on port `1883`
2. Starts the MQTT-to-MySQL ingestion bridge
3. Starts the Risk Prediction Microservice on `http://127.0.0.1:8001`
4. Starts the Backend Orchestration API on `http://127.0.0.1:8000`
5. Starts the Simulated ESP32 node (`fake_esp32.py`)
6. Launches the React dashboard at `http://localhost:5173`

### Option B: Running Individual Services Manually

Open separate terminal windows from the `gridsense/` root:

**Terminal 1 — MQTT Broker:**
```powershell
& "$env:USERPROFILE\tools\mosquitto\mosquitto.exe" -c mosquitto.conf -v
```

**Terminal 2 — Ingestion Bridge:**
```powershell
python ingestion/mqtt_to_mysql.py
```

**Terminal 3 — Simulated ESP32 Feeder:**
```powershell
python ingestion/fake_esp32.py
```

**Terminal 4 — Risk Prediction Microservice:**
```powershell
python -m uvicorn services.risk_api.main:app --host 127.0.0.1 --port 8001
```

**Terminal 5 — Backend Orchestration API:**
```powershell
python -m uvicorn services.backend_api.main:app --host 127.0.0.1 --port 8000
```

**Terminal 6 — Frontend Dashboard:**
```powershell
cd frontend
npm run dev
```
Open your browser at `http://localhost:5173`.

---

## 5. Machine Learning & Model Retraining

The system is equipped with both OpenRouter LLM inference and a local Random Forest model (trained with 99.67% test accuracy).

### How to Retrain Against Real Feeder Telemetry
Once real telemetry points have accumulated in MySQL, you can retrain the local model against historical data:
1. Export telemetry rows from MySQL to CSV:
   ```sql
   SELECT voltage, current, renewable, hosting_index 
   FROM gridsense.feeder_telemetry 
   INTO OUTFILE 'C:/ProgramData/MySQL/MySQL Server 8.0/Uploads/real_feeder_data.csv'
   FIELDS TERMINATED BY ',' ENCLOSED BY '"' LINES TERMINATED BY '\n';
   ```
2. Or use Python to pull real records into `ml/feeder_training_data.csv`:
   ```powershell
   python -c "
   import pymysql, pandas as pd
   conn = pymysql.connect(host='localhost', user='root', password='Nikolatesla369', database='gridsense')
   df = pd.read_sql('SELECT voltage, current, renewable, hosting_index FROM feeder_telemetry', conn)
   # Add ground truth or calculated labels
   df['label'] = df.apply(lambda r: 'critical' if (r['voltage'] < 214 or r['voltage'] > 244 or r['current'] > 52) else ('caution' if (r['voltage'] < 220 or r['voltage'] > 240 or r['current'] > 40) else 'safe'), axis=1)
   df.to_csv('ml/feeder_training_data.csv', index=False)
   "
   ```
3. Retrain the model:
   ```powershell
   python ml/train_model.py
   ```
   The updated model is saved to `ml/risk_model.pkl` and automatically loaded by the risk service upon reload.

---

## 6. Verification Status

| Phase | Description | Result | Details |
|---|---|---|---|
| **Phase 0** | Environment & Config | **PASS** | Python 3.13, Node v24, `.env.example`, `.env` configured |
| **Phase 1** | MQTT Broker & Ingestion | **PASS** | Mosquitto running, `fake_esp32.py` → `mqtt_to_mysql.py` → MySQL verified, malformed payload error handling verified |
| **Phase 2** | ML Risk Pipeline | **PASS** | 6,000 synthetic samples generated, Random Forest model trained with **99.67% test accuracy**, `risk_model.pkl` saved |
| **Phase 3** | Risk Prediction API | **PASS** | FastAPI on port 8001, OpenRouter LLM (`openai/gpt-4o-mini`) + local fallback verified via `/health` & `/predict` |
| **Phase 4** | Backend Orchestration API | **PASS** | FastAPI on port 8000, `/latest`, `/history`, and live WebSocket `/ws/live` streaming verified with live test client |
| **Phase 5** | React Dashboard | **PASS** | Vite + React + Tailwind + Recharts built without errors (`npm run build` PASS, dev server verified) |
| **Phase 6** | ESP32 Firmware Source | **PASS** | `firmware/main.cpp` created with full pinouts for ZMPT101B, SCT-013, SSD1306, 3 status LEDs, matching wire format exactly |
| **Phase 7** | Orchestration & Docs | **PASS** | `run_all.ps1`, `run_all.sh`, `README.md`, `HANDOFF.md` complete |
