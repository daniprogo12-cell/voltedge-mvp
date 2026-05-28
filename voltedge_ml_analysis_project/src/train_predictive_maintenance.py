"""
VoltEdge predictive maintenance demo

This script trains a simple linear regression model on the demo historical
CSV data and adapts the analysis to the current VoltEdge MVP store JSON files:

- data/telemetry_store.json
- data/health_store.json
- data/maintenance_store.json

The JSON files are not large enough to train a real model alone, so the script
uses them as the current operational snapshot that should be scored by the
demo model.

Run:
    python src/train_predictive_maintenance.py
"""

from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
HISTORICAL_DATA_PATH = DATA_DIR / "simulated_yearly_charger_data.csv"
STORE_PATHS = [
    DATA_DIR / "telemetry_store.json",
    DATA_DIR / "health_store.json",
    DATA_DIR / "maintenance_store.json",
]
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

FEATURE_COLS = [
    "avg_health_score",
    "error_count",
    "offline_events",
    "missing_heartbeat_count",
    "avg_power_kw",
    "anomaly_count",
    "previous_incidents",
]
TARGET_COL = "incident_count_next_30_days"


def train_linear_regression(X_train, y_train):
    """Train linear regression with an intercept using numpy least squares."""
    X_design = np.column_stack([np.ones(len(X_train)), X_train])
    coefficients = np.linalg.lstsq(X_design, y_train, rcond=None)[0]
    return coefficients


def predict_linear_regression(X, coefficients):
    """Predict non-negative incident counts."""
    X_design = np.column_stack([np.ones(len(X)), X])
    return np.clip(X_design @ coefficients, 0, None)


def empty_store():
    """Return the common VoltEdge store shape used by the MVP JSON files."""
    return {
        "telemetry_readings": [],
        "health_snapshots": [],
        "anomalies": [],
        "maintenance_recommendations": [],
        "incidents": [],
    }


def load_store_files(paths):
    """
    Merge multiple VoltEdge JSON store files into one in-memory store.

    Each file may contain only one or a few populated collections. Missing
    collections are treated as empty lists, so the script works with split
    exports as well as a single combined export.
    """
    merged = empty_store()

    for path in paths:
        if not path.exists():
            print(f"Warning: store file not found and skipped: {path}")
            continue

        with open(path, "r", encoding="utf-8") as f:
            store = json.load(f)

        for key in merged:
            values = store.get(key, [])
            if values is None:
                values = []
            merged[key].extend(values)

    return merged


def month_start(value):
    """Convert ISO timestamp to month start date string."""
    if value is None:
        return None
    timestamp = pd.to_datetime(value, utc=True).tz_convert(None)
    return timestamp.to_period("M").start_time.date().isoformat()


def latest_month_from_store(store):
    """Find the latest month represented in any timestamped store collection."""
    months = []
    for collection in store.values():
        for item in collection:
            month = month_start(item.get("timestamp"))
            if month:
                months.append(month)
    if not months:
        return pd.Timestamp.today().to_period("M").start_time.date().isoformat()
    return max(months)


def build_current_feature_frame(store):
    """
    Convert current MVP JSON data into one feature row per charger.

    The feature engineering mirrors the historical CSV feature names used by
    the demo model, so the same model can score current chargers.
    """
    charger_ids = set()

    for collection_name in [
        "telemetry_readings",
        "health_snapshots",
        "anomalies",
        "maintenance_recommendations",
        "incidents",
    ]:
        for item in store.get(collection_name, []):
            if item.get("charger_id"):
                charger_ids.add(item["charger_id"])

    if not charger_ids:
        raise ValueError("No charger_id values found in the supplied JSON store files.")

    rows = []
    current_month = latest_month_from_store(store)

    telemetry = pd.DataFrame(store.get("telemetry_readings", []))
    health = pd.DataFrame(store.get("health_snapshots", []))
    anomalies = pd.DataFrame(store.get("anomalies", []))
    incidents = pd.DataFrame(store.get("incidents", []))

    for charger_id in sorted(charger_ids):
        t = telemetry[telemetry["charger_id"] == charger_id] if not telemetry.empty else pd.DataFrame()
        h = health[health["charger_id"] == charger_id] if not health.empty else pd.DataFrame()
        a = anomalies[anomalies["charger_id"] == charger_id] if not anomalies.empty else pd.DataFrame()
        i = incidents[incidents["charger_id"] == charger_id] if not incidents.empty else pd.DataFrame()

        telemetry_count = int(len(t))

        if not h.empty and "health_score" in h.columns:
            avg_health_score = float(pd.to_numeric(h["health_score"], errors="coerce").mean())
        else:
            # Neutral fallback when a charger has telemetry but no health snapshot yet.
            avg_health_score = 75.0

        if not t.empty and "error_code" in t.columns:
            telemetry_error_count = int(t["error_code"].notna().sum())
        else:
            telemetry_error_count = 0

        if not t.empty and "status" in t.columns:
            offline_events = int(t["status"].isin(["offline", "faulted"]).sum())
        else:
            offline_events = 0

        if not t.empty and "heartbeat" in t.columns:
            missing_heartbeat_count = int((t["heartbeat"] == False).sum())  # noqa: E712
        else:
            missing_heartbeat_count = 0

        if not t.empty and "power_kw" in t.columns:
            avg_power_kw = float(pd.to_numeric(t["power_kw"], errors="coerce").fillna(0).mean())
        else:
            avg_power_kw = 0.0

        anomaly_count = int(len(a))
        previous_incidents = int(len(i))

        rows.append(
            {
                "month": current_month,
                "charger_id": charger_id,
                "telemetry_count": telemetry_count,
                "avg_health_score": round(avg_health_score, 2),
                "error_count": telemetry_error_count,
                "offline_events": offline_events,
                "missing_heartbeat_count": missing_heartbeat_count,
                "avg_power_kw": round(avg_power_kw, 2),
                "anomaly_count": anomaly_count,
                "previous_incidents": previous_incidents,
            }
        )

    return pd.DataFrame(rows)


def standardize(X, mu, sigma):
    """Standardize with training-set statistics."""
    sigma = sigma.copy()
    sigma[sigma == 0] = 1
    return (X - mu) / sigma


def risk_category(predicted_incidents):
    """Translate predicted incident count into a simple reporting category."""
    if predicted_incidents >= 1.5:
        return "high"
    if predicted_incidents >= 0.5:
        return "medium"
    return "low"


def operational_risk_category(score):
    """Translate a 0-100 operational risk score into a reporting category."""
    if score >= 70:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def calculate_operational_risk_score(row):
    """
    Calculate a transparent MVP risk score for the current JSON snapshot.

    The ML prediction is kept as the predictive-maintenance demonstration.
    This rule-based score is used for current operational prioritisation because
    the uploaded JSON snapshot is very small and contains direct health/risk
    signals such as health_score, missing heartbeat and incidents.
    """
    score = (
        (100 - float(row["avg_health_score"]))
        + 15 * int(row["error_count"])
        + 20 * int(row["offline_events"])
        + 20 * int(row["missing_heartbeat_count"])
        + 10 * int(row["anomaly_count"])
        + 25 * int(row["previous_incidents"])
    )
    return round(float(min(max(score, 0), 100)), 2)


def main():
    historical_df = pd.read_csv(HISTORICAL_DATA_PATH)

    train_mask = pd.to_datetime(historical_df["month"]) < pd.Timestamp("2026-03-01")

    X_train = historical_df.loc[train_mask, FEATURE_COLS].to_numpy(dtype=float)
    y_train = historical_df.loc[train_mask, TARGET_COL].to_numpy(dtype=float)
    X_test = historical_df.loc[~train_mask, FEATURE_COLS].to_numpy(dtype=float)
    y_test = historical_df.loc[~train_mask, TARGET_COL].to_numpy(dtype=float)
    test_df = historical_df.loc[~train_mask].copy()

    # Standardize features with training-set statistics
    mu = X_train.mean(axis=0)
    sigma = X_train.std(axis=0)
    sigma[sigma == 0] = 1

    X_train_scaled = standardize(X_train, mu, sigma)
    X_test_scaled = standardize(X_test, mu, sigma)

    coefficients = train_linear_regression(X_train_scaled, y_train)
    test_predictions = predict_linear_regression(X_test_scaled, coefficients)

    test_df["predicted_incidents_next_30_days"] = np.round(test_predictions, 2)
    test_df.to_csv(OUTPUT_DIR / "predictions_test_period.csv", index=False)

    mae = float(np.mean(np.abs(y_test - test_predictions)))
    rmse = float(np.sqrt(np.mean((y_test - test_predictions) ** 2)))

    # Load and score current JSON store data
    current_store = load_store_files(STORE_PATHS)
    current_df = build_current_feature_frame(current_store)

    X_current = current_df[FEATURE_COLS].to_numpy(dtype=float)
    X_current_scaled = standardize(X_current, mu, sigma)
    current_predictions = predict_linear_regression(X_current_scaled, coefficients)

    current_df["predicted_incidents_next_30_days"] = np.round(current_predictions, 2)
    current_df["ml_risk_category"] = current_df["predicted_incidents_next_30_days"].apply(risk_category)
    current_df["operational_risk_score"] = current_df.apply(calculate_operational_risk_score, axis=1)
    current_df["operational_risk_category"] = current_df["operational_risk_score"].apply(operational_risk_category)
    current_df = current_df.sort_values(
        ["operational_risk_score", "predicted_incidents_next_30_days", "charger_id"],
        ascending=[False, False, True],
    )

    current_df.to_csv(OUTPUT_DIR / "current_store_risk_predictions.csv", index=False)

    with open(OUTPUT_DIR / "merged_current_store.json", "w", encoding="utf-8") as f:
        json.dump(current_store, f, indent=2, ensure_ascii=False)

    # Diagram 1: historical test validation
    plt.figure(figsize=(8, 5))
    plt.scatter(y_test, test_predictions)
    max_axis = max(float(y_test.max()), float(test_predictions.max()), 1.0)
    plt.plot([0, max_axis], [0, max_axis])
    plt.xlabel("Faktiske incidents næste 30 dage")
    plt.ylabel("Forudsagte incidents næste 30 dage")
    plt.title("Lineær regression: faktisk vs. forudsagt incident-risiko")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "diagram_1_actual_vs_predicted.png", dpi=200)
    plt.close()

    # Diagram 2: current JSON-store risk ranking
    plt.figure(figsize=(9, 5))
    plt.bar(current_df["charger_id"], current_df["operational_risk_score"])
    plt.xlabel("Ladestander")
    plt.ylabel("Operationel risikoscore (0-100)")
    plt.title("Prioritering til maintenance fra aktuelle JSON-data")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "diagram_2_current_store_risk_ranking.png", dpi=200)
    plt.close()

    # Backwards-compatible diagram name expected by the original README
    plt.figure(figsize=(9, 5))
    latest_month = test_df["month"].max()
    latest = test_df[test_df["month"] == latest_month].copy()
    latest = latest.sort_values("predicted_incidents_next_30_days", ascending=False)
    plt.bar(latest["charger_id"], latest["predicted_incidents_next_30_days"])
    plt.xlabel("Ladestander")
    plt.ylabel("Forudsagte incidents næste 30 dage")
    plt.title(f"Historisk testprioritering ({latest_month})")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "diagram_2_charger_risk_ranking.png", dpi=200)
    plt.close()

    summary = {
        "model": "Linear regression using numpy least squares",
        "target": TARGET_COL,
        "features": FEATURE_COLS,
        "training_data": str(HISTORICAL_DATA_PATH.relative_to(BASE_DIR)),
        "current_store_files": [str(path.relative_to(BASE_DIR)) for path in STORE_PATHS],
        "historical_test_metrics": {
            "mae": round(mae, 3),
            "rmse": round(rmse, 3),
        },
        "current_store_record_counts": {
            key: len(value) for key, value in current_store.items()
        },
        "current_top_risk_charger": current_df.iloc[0].to_dict(),
        "coefficients_standardized": {
            "intercept": round(float(coefficients[0]), 4),
            **{
                FEATURE_COLS[i]: round(float(coefficients[i + 1]), 4)
                for i in range(len(FEATURE_COLS))
            },
        },
        "important_note": (
            "The model is trained on synthetic historical demo data. The supplied "
            "JSON store files are used as the current snapshot for scoring, not as "
            "a statistically sufficient training dataset."
        ),
    }

    with open(OUTPUT_DIR / "model_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("Model trained and current JSON stores scored.")
    print(f"Historical MAE: {mae:.3f}")
    print(f"Historical RMSE: {rmse:.3f}")
    print("\nCurrent store risk ranking:")
    print(
        current_df[
            [
                "charger_id",
                "avg_health_score",
                "error_count",
                "offline_events",
                "missing_heartbeat_count",
                "anomaly_count",
                "previous_incidents",
                "predicted_incidents_next_30_days",
                "ml_risk_category",
                "operational_risk_score",
                "operational_risk_category",
            ]
        ].to_string(index=False)
    )
    print(f"\nOutputs written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
