#!/usr/bin/env python3
"""
GridSense - Backend Orchestration API Service
Stitches together MySQL telemetry persistence, Risk Engine (OpenRouter LLM),
and provides REST + live WebSocket streaming for the React dashboard.
"""

import os
import sys
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

import pymysql
from pymysql.cursors import DictCursor
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [backend_api] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("backend_api")

# Load environment configuration
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
else:
    load_dotenv(override=True)

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "gridsense")

RISK_API_URL = os.getenv("RISK_API_URL", "http://127.0.0.1:8001")
BACKEND_API_HOST = os.getenv("BACKEND_API_HOST", "127.0.0.1")
BACKEND_API_PORT = int(os.getenv("BACKEND_API_PORT", 8000))
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

app = FastAPI(
    title="GridSense Backend Orchestration API",
    description="Orchestrates MySQL telemetry persistence, ML/LLM risk assessment, and live WebSocket feed",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_connection():
    """Create a connection to MySQL."""
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        cursorclass=DictCursor,
        connect_timeout=5,
        autocommit=True
    )


def fetch_latest_telemetry() -> Optional[Dict[str, Any]]:
    """Retrieve the most recent telemetry point from MySQL."""
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, voltage, current, renewable, hosting_index
                    FROM feeder_telemetry
                    ORDER BY id DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
                if row and isinstance(row.get("timestamp"), datetime):
                    row["timestamp"] = row["timestamp"].isoformat()
                return row
        finally:
            conn.close()
    except Exception as e:
        logger.error("Database query error in fetch_latest_telemetry: %s", e)
        return None


def fetch_history_telemetry(minutes: int = 15, limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve time-series history for the last N minutes."""
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, timestamp, voltage, current, renewable, hosting_index
                    FROM feeder_telemetry
                    WHERE timestamp >= NOW() - INTERVAL %s MINUTE
                    ORDER BY id ASC
                    LIMIT %s
                """, (minutes, limit))
                rows = cursor.fetchall()
                for r in rows:
                    if isinstance(r.get("timestamp"), datetime):
                        r["timestamp"] = r["timestamp"].isoformat()
                return rows
        finally:
            conn.close()
    except Exception as e:
        logger.error("Database query error in fetch_history_telemetry: %s", e)
        return []


# In-memory risk cache to prevent blocking live WebSocket stream
last_risk_cache = {
    "telemetry_id": None,
    "risk": {
        "risk_level": "safe",
        "confidence": 0.95,
        "analysis": "Feeder parameters within normal operating range.",
        "recommendation": "Standard operation.",
        "source": "initial_state"
    }
}


async def get_risk_prediction(voltage: float, current: float, renewable: float, hosting_index: float, telemetry_id: Optional[int] = None) -> Dict[str, Any]:
    """Call the Risk API service with caching to keep WebSocket high-frequency and non-blocking."""
    global last_risk_cache

    if telemetry_id is not None and last_risk_cache["telemetry_id"] == telemetry_id:
        return last_risk_cache["risk"]

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            payload = {
                "voltage": voltage,
                "current": current,
                "renewable": renewable,
                "hosting_index": hosting_index
            }
            resp = await client.post(f"{RISK_API_URL}/predict", json=payload)
            if resp.status_code == 200:
                risk_data = resp.json()
                last_risk_cache = {
                    "telemetry_id": telemetry_id,
                    "risk": risk_data
                }
                return risk_data
            else:
                logger.warning("Risk API returned status %s: %s", resp.status_code, resp.text)
    except Exception as e:
        logger.warning("Risk API request failed (%s). Generating fallback risk.", e)

    # Local fallback
    risk_level = "safe"
    if voltage < 214 or voltage > 244 or current > 52 or hosting_index < 40:
        risk_level = "critical"
    elif voltage < 220 or voltage > 240 or current > 40 or hosting_index < 70:
        risk_level = "caution"

    fallback_risk = {
        "risk_level": risk_level,
        "confidence": 0.88,
        "analysis": f"Feeder telemetry V={voltage:.1f}V, I={current:.1f}A evaluated via rule baseline.",
        "recommendation": "Monitor feeder stability.",
        "source": "backend_fallback"
    }
    last_risk_cache = {
        "telemetry_id": telemetry_id,
        "risk": fallback_risk
    }
    return fallback_risk


@app.get("/health")
async def health():
    db_ok = False
    try:
        c = get_db_connection()
        c.close()
        db_ok = True
    except Exception:
        pass

    return {
        "status": "ok",
        "service": "backend_api",
        "database_connected": db_ok,
        "risk_api_target": RISK_API_URL
    }


@app.get("/latest")
async def get_latest():
    """Fetch the latest telemetry point with associated risk assessment."""
    latest = fetch_latest_telemetry()
    if not latest:
        return JSONResponse(
            status_code=200,
            content={"status": "no_data", "message": "No feeder telemetry points recorded yet."}
        )

    risk = await get_risk_prediction(
        latest["voltage"], latest["current"], latest["renewable"], latest["hosting_index"], latest.get("id")
    )
    latest["risk"] = risk
    return {"status": "success", "data": latest}


@app.get("/history")
async def get_history(minutes: int = Query(15, ge=1, le=1440), limit: int = Query(100, ge=1, le=500)):
    """Fetch historical telemetry series."""
    rows = fetch_history_telemetry(minutes=minutes, limit=limit)
    return {
        "status": "success",
        "count": len(rows),
        "minutes": minutes,
        "data": rows
    }


@app.post("/simulate-surge")
async def simulate_surge(voltage: float = 248.5, current: float = 56.0, renewable: float = 82.0):
    """Inject a test anomaly into MySQL for live demonstration from the dashboard."""
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Calculate hosting index for surge
                v_dev = abs(voltage - 230.0)
                v_penalty = (v_dev / 20.0) * 40.0
                c_penalty = max(0.0, (current - 35.0) / 25.0) * 35.0
                r_penalty = ((renewable - 60.0) / 20.0) * ((voltage - 235.0) / 10.0) * 25.0 if renewable > 60 and voltage > 235 else 0.0
                hi = round(max(0.0, min(100.0, 100.0 - (v_penalty + c_penalty + r_penalty))), 2)

                cursor.execute("""
                    INSERT INTO feeder_telemetry (voltage, current, renewable, hosting_index)
                    VALUES (%s, %s, %s, %s)
                """, (voltage, current, renewable, hi))
                return {"status": "success", "message": f"Injected surge: V={voltage}V, I={current}A, HI={hi}"}
        finally:
            conn.close()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/risk")
async def get_risk():
    """Get risk assessment for the latest feeder state."""
    latest = fetch_latest_telemetry()
    if not latest:
        return {"status": "no_data", "message": "No feeder data available to compute risk."}

    risk = await get_risk_prediction(
        latest["voltage"], latest["current"], latest["renewable"], latest["hosting_index"], latest.get("id")
    )
    return {
        "status": "success",
        "feeder_snapshot": latest,
        "risk": risk
    }


@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """
    Live telemetry WebSocket stream.
    Broadcasts merged telemetry + AI risk state every ~2 seconds.
    """
    await websocket.accept()
    logger.info("WebSocket client connected: %s", websocket.client)
    try:
        while True:
            latest = fetch_latest_telemetry()
            if latest:
                risk = await get_risk_prediction(
                    latest["voltage"], latest["current"], latest["renewable"], latest["hosting_index"], latest.get("id")
                )
                latest["risk"] = risk
                message = {
                    "type": "telemetry_update",
                    "data": latest
                }
            else:
                message = {
                    "type": "no_data",
                    "message": "Waiting for telemetry stream from feeder node..."
                }

            await websocket.send_text(json.dumps(message))
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected: %s", websocket.client)
    except Exception as e:
        logger.error("WebSocket connection error: %s", e)


def main():
    import uvicorn
    logger.info("Starting Backend Orchestration API on %s:%d...", BACKEND_API_HOST, BACKEND_API_PORT)
    uvicorn.run("services.backend_api.main:app", host=BACKEND_API_HOST, port=BACKEND_API_PORT, reload=False)


if __name__ == "__main__":
    main()
