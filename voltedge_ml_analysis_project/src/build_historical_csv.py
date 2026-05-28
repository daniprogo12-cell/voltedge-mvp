"""
Build a historical, ML-ready CSV from VoltEdge JSON store files.

Input folders:
    data/telemetry/*.json
    data/health/*.json
    data/maintenance/*.json

Output:
    data/generated_historical_charger_data.csv

The generated CSV follows the same structure as the original demo CSV:
    month,
    charger_id,
    telemetry_count,
    avg_health_score,
    error_count,
    offline_events,
    missing_heartbeat_count,
    avg_power_kw,
    anomaly_count,
    previous_incidents,
    incident_count_next_30_days
"""

from __future__ import annotations

from pathlib import Path
import json
from typing import Any

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
TELEMETRY_DIR = DATA_DIR / "telemetry"
HEALTH_DIR = DATA_DIR / "health"
MAINTENANCE_DIR = DATA_DIR / "maintenance"
OUTPUT_CSV = DATA_DIR / "generated_historical_charger_data.csv"

EXPECTED_COLUMNS = [
    "month",
    "charger_id",
    "telemetry_count",
    "avg_health_score",
    "error_count",
    "offline_events",
    "missing_heartbeat_count",
    "avg_power_kw",
    "anomaly_count",
    "previous_incidents",
    "incident_count_next_30_days",
]


def _read_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        content = json.load(file)
    if not isinstance(content, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return content


def _load_records_from_folder(folder: Path, top_level_key: str) -> list[dict[str, Any]]:
    """Load records from all JSON files in a folder.

    Each file is expected to be a VoltEdge store object, for example:
        {"telemetry_readings": [...], "health_snapshots": [...]}.
    Missing keys are treated as empty lists, so files can be partial stores.
    """
    records: list[dict[str, Any]] = []
    if not folder.exists():
        return records

    for path in sorted(folder.glob("*.json")):
        store = _read_json_file(path)
        value = store.get(top_level_key, [])
        if not isinstance(value, list):
            raise ValueError(f"Expected '{top_level_key}' to be a list in {path}")
        records.extend([record for record in value if isinstance(record, dict)])

    return records


def _to_dataframe(records: list[dict[str, Any]], timestamp_column: str = "timestamp") -> pd.DataFrame:
    df = pd.DataFrame(records)
    if df.empty:
        return df
    if timestamp_column in df.columns:
        df[timestamp_column] = pd.to_datetime(df[timestamp_column], errors="coerce", utc=True)
        df = df.dropna(subset=[timestamp_column])
    return df


def _month_start(series: pd.Series) -> pd.Series:
    # Convert UTC timestamps to naive month-start timestamps for simple grouping and CSV output.
    return series.dt.tz_convert(None).dt.to_period("M").dt.to_timestamp()


def _monthly_telemetry_features(telemetry_df: pd.DataFrame) -> pd.DataFrame:
    if telemetry_df.empty:
        return pd.DataFrame(columns=[
            "month", "charger_id", "telemetry_count", "error_count",
            "offline_events", "missing_heartbeat_count", "avg_power_kw"
        ])

    required = ["charger_id", "timestamp"]
    missing = [col for col in required if col not in telemetry_df.columns]
    if missing:
        raise ValueError(f"Telemetry data is missing required columns: {missing}")

    df = telemetry_df.copy()
    df["month"] = _month_start(df["timestamp"])
    df["has_error"] = df.get("error_code", pd.Series(index=df.index)).notna()
    df["is_offline"] = df.get("status", "").astype(str).str.lower().eq("offline")
    df["missing_heartbeat"] = df.get("heartbeat", True).eq(False)
    df["power_kw_numeric"] = pd.to_numeric(df.get("power_kw", 0), errors="coerce").fillna(0)

    grouped = df.groupby(["month", "charger_id"], as_index=False).agg(
        telemetry_count=("charger_id", "size"),
        error_count=("has_error", "sum"),
        offline_events=("is_offline", "sum"),
        missing_heartbeat_count=("missing_heartbeat", "sum"),
        avg_power_kw=("power_kw_numeric", "mean"),
    )
    return grouped


def _monthly_health_features(health_df: pd.DataFrame) -> pd.DataFrame:
    if health_df.empty:
        return pd.DataFrame(columns=["month", "charger_id", "avg_health_score"])

    required = ["charger_id", "timestamp", "health_score"]
    missing = [col for col in required if col not in health_df.columns]
    if missing:
        raise ValueError(f"Health data is missing required columns: {missing}")

    df = health_df.copy()
    df["month"] = _month_start(df["timestamp"])
    df["health_score_numeric"] = pd.to_numeric(df["health_score"], errors="coerce")

    grouped = df.groupby(["month", "charger_id"], as_index=False).agg(
        avg_health_score=("health_score_numeric", "mean"),
    )
    return grouped


def _monthly_anomaly_features(anomaly_df: pd.DataFrame) -> pd.DataFrame:
    if anomaly_df.empty:
        return pd.DataFrame(columns=["month", "charger_id", "anomaly_count"])

    required = ["charger_id", "timestamp"]
    missing = [col for col in required if col not in anomaly_df.columns]
    if missing:
        raise ValueError(f"Anomaly data is missing required columns: {missing}")

    df = anomaly_df.copy()
    df["month"] = _month_start(df["timestamp"])
    grouped = df.groupby(["month", "charger_id"], as_index=False).agg(
        anomaly_count=("charger_id", "size"),
    )
    return grouped


def _incident_features(incident_df: pd.DataFrame, base_rows: pd.DataFrame) -> pd.DataFrame:
    """Calculate previous incidents and incidents in the next 30 days.

    previous_incidents counts incidents before the beginning of the month.
    incident_count_next_30_days counts incidents after the month ends and up to 30 days later.
    """
    result = base_rows[["month", "charger_id"]].copy()
    result["previous_incidents"] = 0
    result["incident_count_next_30_days"] = 0

    if incident_df.empty:
        return result

    required = ["charger_id", "timestamp"]
    missing = [col for col in required if col not in incident_df.columns]
    if missing:
        raise ValueError(f"Incident data is missing required columns: {missing}")

    incidents = incident_df.copy()
    incidents["timestamp"] = incidents["timestamp"].dt.tz_convert(None)

    previous_counts = []
    next_30_counts = []

    for _, row in result.iterrows():
        charger_id = row["charger_id"]
        period_start = pd.Timestamp(row["month"])
        period_end = period_start + pd.offsets.MonthEnd(1)
        next_window_end = period_end + pd.Timedelta(days=30)

        charger_incidents = incidents[incidents["charger_id"] == charger_id]
        previous_counts.append(int((charger_incidents["timestamp"] < period_start).sum()))
        next_30_counts.append(int(((charger_incidents["timestamp"] > period_end) & (charger_incidents["timestamp"] <= next_window_end)).sum()))

    result["previous_incidents"] = previous_counts
    result["incident_count_next_30_days"] = next_30_counts
    return result


def build_historical_csv(output_csv: Path = OUTPUT_CSV) -> pd.DataFrame:
    telemetry_records = _load_records_from_folder(TELEMETRY_DIR, "telemetry_readings")
    health_records = _load_records_from_folder(HEALTH_DIR, "health_snapshots")
    anomaly_records = _load_records_from_folder(HEALTH_DIR, "anomalies")
    incident_records = _load_records_from_folder(MAINTENANCE_DIR, "incidents")

    telemetry_df = _to_dataframe(telemetry_records)
    health_df = _to_dataframe(health_records)
    anomaly_df = _to_dataframe(anomaly_records)
    incident_df = _to_dataframe(incident_records)

    monthly_telemetry = _monthly_telemetry_features(telemetry_df)
    monthly_health = _monthly_health_features(health_df)
    monthly_anomalies = _monthly_anomaly_features(anomaly_df)

    # Build the base grain: one row per charger per month.
    #
    # We use a full monthly grid from the first to the last timestamp found in
    # telemetry, health, anomalies or incidents. This makes the generated file
    # behave like a real historical CSV, even if one month has no telemetry for
    # a charger but still needs to be represented in the time series.
    timestamp_sources = []
    charger_sources = []
    for frame in [telemetry_df, health_df, anomaly_df, incident_df]:
        if not frame.empty:
            if "timestamp" in frame.columns:
                timestamp_sources.append(frame["timestamp"])
            if "charger_id" in frame.columns:
                charger_sources.append(frame["charger_id"].dropna().astype(str))

    if not timestamp_sources or not charger_sources:
        raise ValueError(
            "No usable charger/timestamp rows were found. "
            "Place JSON files in data/telemetry, data/health and data/maintenance."
        )

    all_timestamps = pd.concat(timestamp_sources, ignore_index=True).dropna()
    all_chargers = sorted(pd.concat(charger_sources, ignore_index=True).dropna().unique())

    min_month = all_timestamps.min().tz_convert(None).to_period("M").to_timestamp()
    max_month = all_timestamps.max().tz_convert(None).to_period("M").to_timestamp()
    months = pd.date_range(min_month, max_month, freq="MS")

    base = pd.MultiIndex.from_product(
        [months, all_chargers], names=["month", "charger_id"]
    ).to_frame(index=False)
    base = base.sort_values(["month", "charger_id"]).reset_index(drop=True)

    df = base.merge(monthly_telemetry, on=["month", "charger_id"], how="left")
    df = df.merge(monthly_health, on=["month", "charger_id"], how="left")
    df = df.merge(monthly_anomalies, on=["month", "charger_id"], how="left")
    df = df.merge(_incident_features(incident_df, base), on=["month", "charger_id"], how="left")

    numeric_defaults = {
        "telemetry_count": 0,
        "avg_health_score": 100,
        "error_count": 0,
        "offline_events": 0,
        "missing_heartbeat_count": 0,
        "avg_power_kw": 0,
        "anomaly_count": 0,
        "previous_incidents": 0,
        "incident_count_next_30_days": 0,
    }
    for column, default in numeric_defaults.items():
        if column not in df.columns:
            df[column] = default
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(default)

    # Match original CSV style: month as YYYY-MM-DD and stable column order.
    df["month"] = pd.to_datetime(df["month"]).dt.strftime("%Y-%m-%d")
    df = df[EXPECTED_COLUMNS]

    # Counts should be integers. Averages remain rounded decimals.
    count_cols = [
        "telemetry_count", "error_count", "offline_events", "missing_heartbeat_count",
        "anomaly_count", "previous_incidents", "incident_count_next_30_days",
    ]
    for column in count_cols:
        df[column] = df[column].round().astype(int)
    df["avg_health_score"] = df["avg_health_score"].round(2)
    df["avg_power_kw"] = df["avg_power_kw"].round(3)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    return df


def main() -> None:
    df = build_historical_csv()
    print(f"Historical CSV created: {OUTPUT_CSV}")
    print(f"Rows: {len(df)}")
    print(f"Chargers: {df['charger_id'].nunique()}")
    print(f"Months: {df['month'].nunique()}")


if __name__ == "__main__":
    main()
