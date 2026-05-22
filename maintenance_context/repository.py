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

from datetime import datetime, timezone

from shared.schemas import IncidentStatus
from maintenance_context.models import Incident, MaintenanceRecommendation


class MaintenanceRepository:
    def __init__(self, path: str) -> None:
        self.file = JsonFile(path)

    def add_recommendation(self, recommendation: MaintenanceRecommendation) -> MaintenanceRecommendation:
        data = self.file.read()
        data["maintenance_recommendations"].append(recommendation.model_dump(mode="json"))
        self.file.write(data)
        return recommendation

    def list_recommendations(self, charger_id: str | None = None, limit: int = 100) -> list[MaintenanceRecommendation]:
        rows = self.file.read().get("maintenance_recommendations", [])
        if charger_id:
            rows = [row for row in rows if row.get("charger_id") == charger_id]
        return [MaintenanceRecommendation.model_validate(row) for row in rows[-limit:]]

    def add_incident(self, incident: Incident) -> Incident:
        data = self.file.read()
        data["incidents"].append(incident.model_dump(mode="json"))
        self.file.write(data)
        return incident

    def list_incidents(self, charger_id: str | None = None, status: str | None = None, limit: int = 100) -> list[Incident]:
        rows = self.file.read().get("incidents", [])
        if charger_id:
            rows = [row for row in rows if row.get("charger_id") == charger_id]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return [Incident.model_validate(row) for row in rows[-limit:]]

    def get_open_incident_for_charger(self, charger_id: str) -> Incident | None:
        incidents = self.list_incidents(charger_id=charger_id, status=IncidentStatus.OPEN.value, limit=10000)
        return incidents[-1] if incidents else None

    def resolve_incident(self, incident_id: str) -> Incident | None:
        data = self.file.read()
        for index, row in enumerate(data["incidents"]):
            if row.get("id") == incident_id:
                row["status"] = IncidentStatus.RESOLVED.value
                row["resolved_at"] = datetime.now(timezone.utc).isoformat()
                data["incidents"][index] = row
                self.file.write(data)
                return Incident.model_validate(row)
        return None

    def reset(self) -> None:
        self.file.reset()
