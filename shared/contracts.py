from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from shared.schemas import (
    Anomaly,
    HealthSnapshot,
    Incident,
    MaintenanceRecommendation,
    TelemetryReading,
)


class TelemetryStoredEvent(BaseModel):
    reading: TelemetryReading
    recent_readings: List[TelemetryReading] = Field(default_factory=list)


class HealthEvaluatedEvent(BaseModel):
    snapshot: HealthSnapshot
    anomalies: List[Anomaly] = Field(default_factory=list)


class MaintenanceDecisionResponse(BaseModel):
    recommendation: Optional[MaintenanceRecommendation] = None
    incident: Optional[Incident] = None
    domain_events: List[str] = Field(default_factory=list)


class TelemetryIngestResponse(BaseModel):
    telemetry: TelemetryReading
    health: Optional[HealthSnapshot] = None
    anomalies: List[Anomaly] = Field(default_factory=list)
    maintenance_recommendation: Optional[MaintenanceRecommendation] = None
    incident: Optional[Incident] = None
    domain_events: List[str] = Field(default_factory=list)
