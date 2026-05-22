from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any


DEFAULT_DATA = {
    "telemetry_readings": [],
    "health_snapshots": [],
    "anomalies": [],
    "maintenance_recommendations": [],
    "incidents": [],
}


class JsonFile:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        if not self.path.exists():
            self.write(DEFAULT_DATA.copy())

    def read(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                self.write(DEFAULT_DATA.copy())
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            for key, value in DEFAULT_DATA.items():
                data.setdefault(key, list(value))
            return data

    def write(self, data: dict[str, Any]) -> None:
        with self._lock:
            temp_path = self.path.with_suffix(".tmp")
            with temp_path.open("w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, ensure_ascii=False)
            temp_path.replace(self.path)

    def reset(self) -> None:
        self.write(DEFAULT_DATA.copy())

from health_context.models import Anomaly, HealthSnapshot


class HealthRepository:
    def __init__(self, path: str) -> None:
        self.file = JsonFile(path)

    def add_snapshot(self, snapshot: HealthSnapshot) -> HealthSnapshot:
        data = self.file.read()
        data["health_snapshots"].append(snapshot.model_dump(mode="json"))
        self.file.write(data)
        return snapshot

    def add_anomaly(self, anomaly: Anomaly) -> Anomaly:
        data = self.file.read()
        data["anomalies"].append(anomaly.model_dump(mode="json"))
        self.file.write(data)
        return anomaly

    def list_snapshots(self, charger_id: str | None = None, limit: int = 100) -> list[HealthSnapshot]:
        rows = self.file.read().get("health_snapshots", [])
        if charger_id:
            rows = [row for row in rows if row.get("charger_id") == charger_id]
        return [HealthSnapshot.model_validate(row) for row in rows[-limit:]]

    def latest_by_charger(self) -> list[HealthSnapshot]:
        latest: dict[str, HealthSnapshot] = {}
        for snapshot in self.list_snapshots(limit=10000):
            current = latest.get(snapshot.charger_id)
            if current is None or snapshot.timestamp > current.timestamp:
                latest[snapshot.charger_id] = snapshot
        return list(latest.values())

    def list_anomalies(self, charger_id: str | None = None, limit: int = 100) -> list[Anomaly]:
        rows = self.file.read().get("anomalies", [])
        if charger_id:
            rows = [row for row in rows if row.get("charger_id") == charger_id]
        return [Anomaly.model_validate(row) for row in rows[-limit:]]

    def reset(self) -> None:
        self.file.reset()
