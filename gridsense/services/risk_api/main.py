#!/usr/bin/env python3
"""
GridSense - AI Risk Prediction Microservice
Provides real-time electrical grid distribution feeder risk classification
powered by OpenRouter LLM (openai/gpt-4o-mini) with local RandomForest fallback.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

import httpx
import joblib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [risk_api] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("risk_api")

# Load environment configuration
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
RISK_API_HOST = os.getenv("RISK_API_HOST", "127.0.0.1")
RISK_API_PORT = int(os.getenv("RISK_API_PORT", 8001))

# Load local ML model artifact as fallback
ML_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "ml" / "risk_model.pkl"
local_model_artifact = None
if ML_MODEL_PATH.exists():
    try:
        local_model_artifact = joblib.load(ML_MODEL_PATH)
        logger.info("Loaded local Random Forest fallback model from %s", ML_MODEL_PATH)
    except Exception as e:
        logger.warning("Could not load local model artifact: %s", e)

app = FastAPI(
    title="GridSense Risk Prediction Microservice",
    description="LLM-powered Feeder Risk Assessment Engine via OpenRouter",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SensorInput(BaseModel):
    voltage: float = Field(..., description="Distribution Feeder RMS Voltage (V)", example=231.5)
    current: float = Field(..., description="Feeder RMS Current (A)", example=28.4)
    renewable: float = Field(..., description="Renewable Generation Penetration (%)", example=45.0)
    hosting_index: Optional[float] = Field(None, description="Hosting Capacity Index (0-100)", example=85.0)


class RiskOutput(BaseModel):
    risk_level: str = Field(..., description="Feeder Risk Classification: safe, caution, or critical")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0")
    analysis: str = Field(..., description="Engineering diagnosis and reasoning")
    recommendation: str = Field(..., description="Recommended mitigation or operational action")
    source: str = Field(..., description="Inference engine source (openrouter_llm or local_rf_model)")


def predict_local_rf(voltage: float, current: float, renewable: float) -> Dict[str, Any]:
    """Inference using local Random Forest model."""
    if not local_model_artifact or "model" not in local_model_artifact:
        # Simple heuristic if no model loaded
        if voltage < 214 or voltage > 244 or current > 52:
            return {"risk_level": "critical", "confidence": 0.90, "analysis": "Voltage or current exceeds safety thresholds.", "recommendation": "Inspect feeder protection and load shedding.", "source": "heuristic_fallback"}
        elif voltage < 220 or voltage > 240 or current > 40:
            return {"risk_level": "caution", "confidence": 0.85, "analysis": "Feeder approaching operating margins.", "recommendation": "Monitor renewable fluctuations.", "source": "heuristic_fallback"}
        return {"risk_level": "safe", "confidence": 0.95, "analysis": "Feeder parameters within optimal boundaries.", "recommendation": "Maintain normal operation.", "source": "heuristic_fallback"}

    clf = local_model_artifact["model"]
    features = [[voltage, current, renewable]]
    risk_level = clf.predict(features)[0]
    probs = clf.predict_proba(features)[0]
    confidence = round(float(max(probs)), 3)

    explanations = {
        "safe": ("Feeder operating within normal thermal and voltage margins.", "Maintain standard dispatch and monitoring."),
        "caution": ("Telemetry indicates approaching voltage boundaries or moderate thermal loading.", "Prepare reactive power compensation and monitor trends."),
        "critical": ("Severe voltage excursion or dangerous overcurrent detected on feeder.", "Alert substation operator; evaluate immediate load curtailment.")
    }
    analysis, rec = explanations.get(risk_level, ("Monitored state.", "Continue monitoring."))

    return {
        "risk_level": risk_level,
        "confidence": confidence,
        "analysis": analysis,
        "recommendation": rec,
        "source": "local_rf_model"
    }


async def predict_openrouter_llm(voltage: float, current: float, renewable: float, hosting_index: Optional[float]) -> Dict[str, Any]:
    """Inference using OpenRouter LLM API (openai/gpt-4o-mini)."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not configured in environment.")

    hi_str = f"{hosting_index:.1f}" if hosting_index is not None else "N/A"

    system_prompt = (
        "You are an electrical distribution grid protection AI. Analyze the feeder telemetry: "
        "nominal voltage is 230V AC (+/-6% standard, 216-244V), rated feeder current is 50A (critical above 52A), "
        "high renewable penetration combined with high voltage causes overvoltage risk. "
        "Return STRICT JSON only with keys:\n"
        "{\n"
        '  "risk_level": "safe" | "caution" | "critical",\n'
        '  "confidence": float (0.80 to 0.99),\n'
        '  "analysis": "crisp 1-2 sentence engineering diagnosis",\n'
        '  "recommendation": "1 sentence mitigation action"\n'
        "}"
    )

    user_prompt = (
        f"Distribution Feeder Telemetry:\n"
        f"- RMS Voltage: {voltage:.2f} V\n"
        f"- RMS Current: {current:.2f} A\n"
        f"- Renewable Penetration: {renewable:.1f} %\n"
        f"- Hosting Capacity Index: {hi_str} / 100\n\n"
        f"Provide the risk classification JSON."
    )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "GridSense Risk Engine"
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 200
    }

    async with httpx.AsyncClient(timeout=4.0) as client:
        resp = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"OpenRouter API error (HTTP {resp.status_code}): {resp.text}")

        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        parsed = json.loads(content)

        risk_level = parsed.get("risk_level", "safe").lower()
        if risk_level not in ["safe", "caution", "critical"]:
            risk_level = "caution"

        confidence = float(parsed.get("confidence", 0.95))
        confidence = max(0.5, min(1.0, confidence))

        return {
            "risk_level": risk_level,
            "confidence": round(confidence, 2),
            "analysis": parsed.get("analysis", "LLM grid state assessment completed."),
            "recommendation": parsed.get("recommendation", "Continue feeder monitoring."),
            "source": f"openrouter_llm ({OPENROUTER_MODEL})"
        }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "risk_api",
        "openrouter_configured": bool(OPENROUTER_API_KEY),
        "openrouter_model": OPENROUTER_MODEL,
        "local_fallback_available": local_model_artifact is not None
    }


@app.post("/predict", response_model=RiskOutput)
async def predict_risk(sensor: SensorInput):
    """
    Evaluate real-time risk level of feeder telemetry.
    Attempts OpenRouter LLM inference first, seamlessly falling back
    to the local Random Forest model if network issues occur.
    """
    if OPENROUTER_API_KEY:
        try:
            res = await predict_openrouter_llm(sensor.voltage, sensor.current, sensor.renewable, sensor.hosting_index)
            return RiskOutput(**res)
        except Exception as e:
            logger.warning("OpenRouter LLM call failed (%s). Falling back to local RF model.", e)

    # Fallback to local model
    res = predict_local_rf(sensor.voltage, sensor.current, sensor.renewable)
    return RiskOutput(**res)


def main():
    import uvicorn
    logger.info("Starting Risk Prediction Microservice on %s:%d...", RISK_API_HOST, RISK_API_PORT)
    uvicorn.run("services.risk_api.main:app", host=RISK_API_HOST, port=RISK_API_PORT, reload=False)


if __name__ == "__main__":
    main()
