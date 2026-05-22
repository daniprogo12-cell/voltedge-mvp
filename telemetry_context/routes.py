from __future__ import annotations

import os

from fastapi import APIRouter, Query

from telemetry_context.models import TelemetryCreate, TelemetryIngestResponse
from telemetry_context.repository import TelemetryRepository
from telemetry_context.service import TelemetryService

router = APIRouter()
repository = TelemetryRepository(os.getenv("JSON_STORE_PATH", "data/telemetry_store.json"))
service = TelemetryService(repository, os.getenv("HEALTH_API_URL", "http://health-api:8000"))


@router.get("/")
def root():
    return {"service": "Telemetry Service", "bounded_context": "Telemetry Context"}


@router.post("/telemetry", response_model=TelemetryIngestResponse)
async def ingest_telemetry(payload: TelemetryCreate):
    return await service.ingest(payload)


@router.get("/telemetry")
def list_telemetry(charger_id: str | None = None, limit: int = Query(default=100, ge=1, le=1000)):
    return repository.list(charger_id=charger_id, limit=limit)


@router.delete("/data/reset")
def reset_data():
    repository.reset()
    return {"status": "reset", "context": "telemetry"}
