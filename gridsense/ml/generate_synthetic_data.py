#!/usr/bin/env python3
"""
GridSense - Synthetic Training Data Generator
Generates realistic distribution feeder operating conditions and labels them
into 'safe', 'caution', or 'critical' risk states based on grid physics
and Hosting Capacity Index calculations.
"""

import os
import random
import pandas as pd
import numpy as np
from pathlib import Path


def compute_hosting_index(voltage: float, current: float, renewable: float) -> float:
    """
    Standardized Hosting Capacity Index (0.0 to 100.0).
    Matches formula in ingestion/fake_esp32.py and firmware/main.cpp.
    """
    v_dev = abs(voltage - 230.0)
    v_penalty = (v_dev / 20.0) * 40.0
    c_penalty = max(0.0, (current - 35.0) / 25.0) * 35.0

    r_penalty = 0.0
    if renewable > 60.0 and voltage > 235.0:
        r_penalty = ((renewable - 60.0) / 20.0) * ((voltage - 235.0) / 10.0) * 25.0
    elif current > 45.0 and renewable < 30.0:
        r_penalty = ((30.0 - renewable) / 20.0) * 15.0

    raw_hi = 100.0 - (v_penalty + c_penalty + r_penalty)
    return round(max(0.0, min(100.0, raw_hi)), 2)


def assign_risk_label(voltage: float, current: float, renewable: float, hi: float) -> str:
    """
    Classify feeder operating state:
      - 'critical': Voltage out of legal limits (<214V or >244V), severe thermal overload (>52A), or HI < 40.
      - 'caution': Approaching limits (214-220V or 240-244V), heavy load (40-52A), or HI in [40, 70).
      - 'safe': Normal nominal voltage (220-240V), moderate load (<40A), and HI >= 70.
    """
    if voltage < 214.0 or voltage > 244.0 or current > 52.0 or hi < 40.0:
        return "critical"
    elif (voltage < 220.0 or voltage > 240.0 or (40.0 <= current <= 52.0) or (40.0 <= hi < 70.0)):
        return "caution"
    else:
        return "safe"


def generate_dataset(num_samples: int = 6000, seed: int = 42) -> pd.DataFrame:
    random.seed(seed)
    np.random.seed(seed)

    rows = []

    for _ in range(num_samples):
        regime = random.choices(
            ["nominal", "high_load", "solar_swell", "sag", "extreme"],
            weights=[0.45, 0.20, 0.15, 0.12, 0.08]
        )[0]

        if regime == "nominal":
            v = random.gauss(230.0, 3.0)
            c = random.uniform(10.0, 35.0)
            r = random.uniform(25.0, 65.0)
        elif regime == "high_load":
            v = random.gauss(224.0, 4.0)
            c = random.uniform(38.0, 56.0)
            r = random.uniform(15.0, 40.0)
        elif regime == "solar_swell":
            v = random.gauss(238.0, 3.5)
            c = random.uniform(12.0, 32.0)
            r = random.uniform(65.0, 95.0)
        elif regime == "sag":
            v = random.gauss(214.0, 4.0)
            c = random.uniform(40.0, 58.0)
            r = random.uniform(10.0, 30.0)
        else:  # extreme
            v = random.choice([random.uniform(205.0, 213.0), random.uniform(245.0, 255.0)])
            c = random.uniform(50.0, 65.0)
            r = random.uniform(10.0, 90.0)

        v = round(float(np.clip(v, 205.0, 255.0)), 2)
        c = round(float(np.clip(c, 5.0, 65.0)), 2)
        r = round(float(np.clip(r, 5.0, 100.0)), 2)

        hi = compute_hosting_index(v, c, r)
        label = assign_risk_label(v, c, r, hi)

        rows.append({
            "voltage": v,
            "current": c,
            "renewable": r,
            "hosting_index": hi,
            "label": label
        })

    df = pd.DataFrame(rows)
    return df


def main():
    output_dir = Path(__file__).resolve().parent
    output_path = output_dir / "feeder_training_data.csv"

    print("Generating 6,000 synthetic feeder telemetry records...")
    df = generate_dataset(num_samples=6000)

    # Save CSV with required columns (voltage, current, renewable, label)
    # Also keeping hosting_index as feature if needed
    export_df = df[["voltage", "current", "renewable", "label"]]
    export_df.to_csv(output_path, index=False)

    print(f"Successfully generated dataset at: {output_path}")
    print("Class distribution:")
    print(df["label"].value_counts(normalize=True).apply(lambda x: f"{x:.1%}"))


if __name__ == "__main__":
    main()
