#!/usr/bin/env python3
"""
GridSense - Feeder Risk Classifier Training Pipeline
Trains a Scikit-Learn RandomForestClassifier to predict grid risk levels
(safe, caution, critical) from live telemetry features (voltage, current, renewable).
Saves the trained model artifact to ml/risk_model.pkl.
"""

import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix


def train():
    ml_dir = Path(__file__).resolve().parent
    data_path = ml_dir / "feeder_training_data.csv"
    model_path = ml_dir / "risk_model.pkl"

    if not data_path.exists():
        print(f"Error: {data_path} not found. Running generate_synthetic_data.py first...")
        from generate_synthetic_data import main as gen_data
        gen_data()

    print(f"Loading training data from: {data_path}")
    df = pd.read_csv(data_path)

    features = ["voltage", "current", "renewable"]
    target = "label"

    X = df[features]
    y = df[target]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print(f"Training set: {len(X_train)} samples | Test set: {len(X_test)} samples")

    # Hyperparameters tuned for speed, generalization and low latency inference
    clf = RandomForestClassifier(
        n_estimators=100,
        max_depth=12,
        min_samples_split=4,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )

    print("Training RandomForestClassifier...")
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)

    print("\n=======================================================")
    print(f"MODEL EVALUATION ON HELD-OUT TEST SPLIT (20%):")
    print(f"Overall Accuracy: {accuracy:.4f} ({accuracy * 100:.2f}%)")
    print("=======================================================\n")
    print("Classification Report:")
    print(classification_report(y_test, y_pred, digits=4))

    print("Confusion Matrix:")
    labels = sorted(list(set(y)))
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    cm_df = pd.DataFrame(cm, index=[f"True_{l}" for l in labels], columns=[f"Pred_{l}" for l in labels])
    print(cm_df)

    # Save model artifact
    # Save a dictionary with model + feature names + classes
    artifact = {
        "model": clf,
        "features": features,
        "classes": list(clf.classes_),
        "version": "1.0.0",
        "accuracy": float(accuracy)
    }
    joblib.dump(artifact, model_path)
    print(f"\nTrained risk model successfully saved to: {model_path}")
    return accuracy


if __name__ == "__main__":
    train()
