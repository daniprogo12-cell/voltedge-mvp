from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from shared.utils import utc_now


class ChargerStatus(str, Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    CHARGING = "charging"
    FAULTED = "faulted"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IncidentStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class RecommendationStatus(str, Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    COMPLETED = "completed"


class TelemetryCreate(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    charger_id: str = Field(..., min_length=1, examples=["CH-001"])
    connector_id: str = Field(default="1")
    timestamp: datetime = Field(default_factory=utc_now)
    status: ChargerStatus = Field(..., examples=["available", "charging", "faulted", "offline"])
    power_kw: float = Field(default=0, ge=0)
    voltage: Optional[float] = Field(default=None, ge=0)
    current: Optional[float] = Field(default=None, ge=0)
    error_code: Optional[str] = Field(default=None, examples=["E_CONN_01"])
    heartbeat: bool = Field(default=True, validation_alias=AliasChoices("heartbeat", "heartbeat_ok"))

    @field_validator("error_code")
    @classmethod
    def normalize_error_code(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class TelemetryReading(TelemetryCreate):
    id: str = Field(default_factory=lambda: str(uuid4()))


class HealthSnapshot(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    charger_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    source_telemetry_id: str
    health_score: int = Field(..., ge=0, le=100)
    health_status: HealthStatus
    risk_level: RiskLevel
    fault_indicators: List[str] = Field(default_factory=list)
    recommendation_text: str


class Anomaly(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    charger_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    source_telemetry_id: str
    anomaly_type: str
    severity: RiskLevel
    description: str


class MaintenanceRecommendation(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    charger_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    source_health_snapshot_id: str
    risk_level: RiskLevel
    action: str
    reason: str
    status: RecommendationStatus = RecommendationStatus.OPEN


class Incident(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    charger_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    source_health_snapshot_id: str
    severity: RiskLevel
    status: IncidentStatus = IncidentStatus.OPEN
    title: str
    description: str
    resolved_at: Optional[datetime] = None
