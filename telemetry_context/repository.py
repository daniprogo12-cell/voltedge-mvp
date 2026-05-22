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

from telemetry_context.models import TelemetryReading


class TelemetryRepository:
    def __init__(self, path: str) -> None:
        self.file = JsonFile(path)

    def add(self, reading: TelemetryReading) -> TelemetryReading:
        data = self.file.read()
        data["telemetry_readings"].append(reading.model_dump(mode="json"))
        self.file.write(data)
        return reading

    def list(self, charger_id: str | None = None, limit: int = 100) -> list[TelemetryReading]:
        rows = self.file.read().get("telemetry_readings", [])
        if charger_id:
            rows = [row for row in rows if row.get("charger_id") == charger_id]
        return [TelemetryReading.model_validate(row) for row in rows[-limit:]]

    def reset(self) -> None:
        self.file.reset()
