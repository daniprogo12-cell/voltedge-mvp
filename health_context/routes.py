from __future__ import annotations

import os

from fastapi import APIRouter, Query

from health_context.models import TelemetryStoredEvent
from health_context.repository import HealthRepository
from health_context.service import HealthService

router = APIRouter()
repository = HealthRepository(os.getenv("JSON_STORE_PATH", "data/health_store.json"))
service = HealthService(repository, os.getenv("MAINTENANCE_API_URL", "http://maintenance-api:8000"))


@router.get("/")
def root():
    return {"service": "Health Service", "bounded_context": "Charger Health Context"}


@router.post("/health/evaluate")
async def evaluate_health(event: TelemetryStoredEvent):
    return await service.evaluate(event)


@router.get("/health")
def list_health(charger_id: str | None = None, limit: int = Query(default=100, ge=1, le=1000)):
    return repository.list_snapshots(charger_id=charger_id, limit=limit)


@router.get("/health/latest")
def latest_health():
    return repository.latest_by_charger()


@router.get("/anomalies")
def list_anomalies(charger_id: str | None = None, limit: int = Query(default=100, ge=1, le=1000)):
    return repository.list_anomalies(charger_id=charger_id, limit=limit)


@router.delete("/data/reset")
def reset_data():
    repository.reset()
    return {"status": "reset", "context": "health"}
