from __future__ import annotations

from typing import Any

import httpx

from health_context.models import HealthEvaluatedEvent, TelemetryStoredEvent
from health_context.repository import HealthRepository
from shared.schemas import (
    Anomaly,
    ChargerStatus,
    HealthSnapshot,
    HealthStatus,
    MaintenanceRecommendation,
    RiskLevel,
    TelemetryReading,
)


class HealthScoreCalculator:
    @staticmethod
    def calculate(reading: TelemetryReading, recent_readings: list[TelemetryReading]) -> HealthSnapshot:
        score = 100
        indicators: list[str] = []
        status = ChargerStatus(reading.status)

        if not reading.heartbeat:
            score -= 35
            indicators.append("missing_heartbeat")
        if status == ChargerStatus.FAULTED:
            score -= 40
            indicators.append("charger_faulted")
        elif status == ChargerStatus.OFFLINE:
            score -= 35
            indicators.append("charger_offline")
        elif status == ChargerStatus.UNKNOWN:
            score -= 15
            indicators.append("unknown_status")
        if reading.error_code:
            score -= 20
            indicators.append(f"error_code:{reading.error_code}")
        if status == ChargerStatus.CHARGING and reading.power_kw <= 0.1:
            score -= 15
            indicators.append("charging_without_power")

        same_error_count = sum(1 for item in recent_readings[-5:] if item.error_code and item.error_code == reading.error_code)
        if reading.error_code and same_error_count >= 3:
            score -= 15
            indicators.append("repeated_error_code")

        offline_count = sum(1 for item in recent_readings[-5:] if ChargerStatus(item.status) == ChargerStatus.OFFLINE or not item.heartbeat)
        if offline_count >= 3:
            score -= 15
            indicators.append("repeated_connectivity_loss")

        score = max(0, min(100, score))
        health_status = HealthScoreCalculator.classify(score)
        risk_level = HealthScoreCalculator.risk_level(health_status, indicators)
        recommendation = HealthScoreCalculator.recommendation(risk_level, indicators)

        return HealthSnapshot(
            charger_id=reading.charger_id,
            source_telemetry_id=reading.id,
            health_score=score,
            health_status=health_status,
            risk_level=risk_level,
            fault_indicators=indicators,
            recommendation_text=recommendation,
        )

    @staticmethod
    def classify(score: int) -> HealthStatus:
        if score >= 80:
            return HealthStatus.HEALTHY
        if score >= 50:
            return HealthStatus.DEGRADED
        return HealthStatus.CRITICAL

    @staticmethod
    def risk_level(status: HealthStatus, indicators: list[str]) -> RiskLevel:
        if status == HealthStatus.CRITICAL:
            return RiskLevel.HIGH
        if status == HealthStatus.DEGRADED:
            if "missing_heartbeat" in indicators or "charger_faulted" in indicators:
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @staticmethod
    def recommendation(risk: RiskLevel, indicators: list[str]) -> str:
        if risk == RiskLevel.HIGH:
            if "missing_heartbeat" in indicators or "repeated_connectivity_loss" in indicators:
                return "Check network connection and charger heartbeat immediately."
            if "charger_faulted" in indicators or any(item.startswith("error_code") for item in indicators):
                return "Create operational follow-up and inspect charger error state."
            return "Escalate charger for urgent maintenance review."
        if risk == RiskLevel.MEDIUM:
            return "Monitor charger and schedule preventive maintenance if pattern continues."
        return "No immediate action required."


class AnomalyDetectionService:
    @staticmethod
    def detect(reading: TelemetryReading, snapshot: HealthSnapshot, recent_readings: list[TelemetryReading]) -> list[Anomaly]:
        anomalies: list[Anomaly] = []
        status = ChargerStatus(reading.status)

        if not reading.heartbeat:
            anomalies.append(Anomaly(charger_id=reading.charger_id, source_telemetry_id=reading.id, anomaly_type="heartbeat_missing", severity=RiskLevel.HIGH, description="Charger did not send heartbeat in latest telemetry reading."))
        if status == ChargerStatus.CHARGING and reading.power_kw <= 0.1:
            anomalies.append(Anomaly(charger_id=reading.charger_id, source_telemetry_id=reading.id, anomaly_type="charging_without_power", severity=RiskLevel.MEDIUM, description="Charger reports charging, but power is close to zero."))

        same_error_count = sum(1 for item in recent_readings[-5:] if item.error_code and item.error_code == reading.error_code)
        if reading.error_code and same_error_count >= 3:
            anomalies.append(Anomaly(charger_id=reading.charger_id, source_telemetry_id=reading.id, anomaly_type="repeated_error_code", severity=RiskLevel.HIGH, description=f"Error code {reading.error_code} occurred {same_error_count} times in the latest readings."))
        if snapshot.risk_level == RiskLevel.HIGH and not anomalies:
            anomalies.append(Anomaly(charger_id=reading.charger_id, source_telemetry_id=reading.id, anomaly_type="high_failure_risk", severity=RiskLevel.HIGH, description="Health score and fault indicators indicate high failure risk."))
        return anomalies


class HealthService:
    def __init__(self, repository: HealthRepository, maintenance_api_url: str) -> None:
        self.repository = repository
        self.maintenance_api_url = maintenance_api_url

    async def evaluate(self, event: TelemetryStoredEvent) -> dict[str, Any]:
        domain_events: list[str] = []
        snapshot = HealthScoreCalculator.calculate(event.reading, event.recent_readings)
        self.repository.add_snapshot(snapshot)
        domain_events.extend(["HealthScoreCalculated", "ChargerHealthClassified"])

        anomalies = AnomalyDetectionService.detect(event.reading, snapshot, event.recent_readings)
        for anomaly in anomalies:
            self.repository.add_anomaly(anomaly)

        domain_events.append("FailureRiskEvaluated")
        if anomalies:
            domain_events.append("AlertTriggered")

        maintenance_response = await self._call_maintenance_context(HealthEvaluatedEvent(snapshot=snapshot, anomalies=anomalies))
        domain_events.extend(maintenance_response.get("domain_events", []))

        return {
            "snapshot": snapshot,
            "anomalies": anomalies,
            "maintenance": maintenance_response,
            "domain_events": domain_events,
        }

    async def _call_maintenance_context(self, event: HealthEvaluatedEvent) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.maintenance_api_url}/maintenance/decide",
                json=event.model_dump(mode="json"),
            )
            response.raise_for_status()
            return response.json()
