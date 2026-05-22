from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query

from maintenance_context.models import HealthEvaluatedEvent, MaintenanceDecisionResponse
from maintenance_context.repository import MaintenanceRepository
from maintenance_context.service import MaintenanceService

router = APIRouter()
repository = MaintenanceRepository(os.getenv("JSON_STORE_PATH", "data/maintenance_store.json"))
service = MaintenanceService(repository)


@router.get("/")
def root():
    return {"service": "Maintenance Service", "bounded_context": "Incident & Maintenance Context"}


@router.post("/maintenance/decide", response_model=MaintenanceDecisionResponse)
def decide_maintenance(event: HealthEvaluatedEvent):
    return service.decide(event)


@router.get("/maintenance/recommendations")
def list_recommendations(charger_id: str | None = None, limit: int = Query(default=100, ge=1, le=1000)):
    return repository.list_recommendations(charger_id=charger_id, limit=limit)


@router.get("/maintenance/incidents")
def list_incidents(
    charger_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    return repository.list_incidents(charger_id=charger_id, status=status, limit=limit)


@router.post("/maintenance/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: str):
    incident = repository.resolve_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.delete("/data/reset")
def reset_data():
    repository.reset()
    return {"status": "reset", "context": "maintenance"}
