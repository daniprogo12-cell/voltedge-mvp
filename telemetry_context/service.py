from __future__ import annotations

from typing import Any

import httpx

from telemetry_context.models import (
    TelemetryCreate,
    TelemetryIngestResponse,
    TelemetryReading,
    TelemetryStoredEvent,
)
from telemetry_context.repository import TelemetryRepository


class TelemetryService:
    def __init__(self, repository: TelemetryRepository, health_api_url: str) -> None:
        self.repository = repository
        self.health_api_url = health_api_url

    async def ingest(self, payload: TelemetryCreate) -> TelemetryIngestResponse:
        domain_events = ["TelemetryReceived", "TelemetryValidated"]
        reading = TelemetryReading(**payload.model_dump())
        self.repository.add(reading)
        domain_events.append("TelemetryStored")

        event = TelemetryStoredEvent(
            reading=reading,
            recent_readings=self.repository.list(charger_id=reading.charger_id, limit=20),
        )
        health_response = await self._call_health_context(event)
        domain_events.extend(health_response.get("domain_events", []))

        return TelemetryIngestResponse(
            telemetry=reading,
            health=health_response.get("snapshot"),
            anomalies=health_response.get("anomalies", []),
            maintenance_recommendation=health_response.get("maintenance", {}).get("recommendation"),
            incident=health_response.get("maintenance", {}).get("incident"),
            domain_events=domain_events,
        )

    async def _call_health_context(self, event: TelemetryStoredEvent) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.health_api_url}/health/evaluate",
                json=event.model_dump(mode="json"),
            )
            response.raise_for_status()
            return response.json()
