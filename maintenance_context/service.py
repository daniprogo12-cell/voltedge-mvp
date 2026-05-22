from __future__ import annotations

from typing import Optional

from maintenance_context.models import (
    HealthEvaluatedEvent,
    Incident,
    MaintenanceDecisionResponse,
    MaintenanceRecommendation,
)
from maintenance_context.repository import MaintenanceRepository
from shared.schemas import Anomaly, HealthSnapshot, HealthStatus, RiskLevel


class MaintenanceDecisionPolicy:
    @staticmethod
    def create_recommendation_if_needed(
        snapshot: HealthSnapshot,
        anomalies: list[Anomaly],
    ) -> Optional[MaintenanceRecommendation]:
        if snapshot.risk_level == RiskLevel.LOW and not anomalies:
            return None

        action = "Escalate to operations team" if snapshot.risk_level == RiskLevel.HIGH else "Schedule preventive maintenance review"
        reason_parts = [snapshot.recommendation_text]
        if anomalies:
            reason_parts.append("Detected anomalies: " + ", ".join(item.anomaly_type for item in anomalies))

        return MaintenanceRecommendation(
            charger_id=snapshot.charger_id,
            source_health_snapshot_id=snapshot.id,
            risk_level=snapshot.risk_level,
            action=action,
            reason=" ".join(reason_parts),
        )


class MaintenanceService:
    def __init__(self, repository: MaintenanceRepository) -> None:
        self.repository = repository

    def decide(self, event: HealthEvaluatedEvent) -> MaintenanceDecisionResponse:
        domain_events: list[str] = []
        snapshot = event.snapshot

        recommendation = MaintenanceDecisionPolicy.create_recommendation_if_needed(snapshot, event.anomalies)
        if recommendation:
            self.repository.add_recommendation(recommendation)
            domain_events.append("MaintenanceRecommendationCreated")

        incident = None
        if snapshot.risk_level == RiskLevel.HIGH or snapshot.health_status == HealthStatus.CRITICAL:
            existing = self.repository.get_open_incident_for_charger(snapshot.charger_id)
            if existing:
                incident = existing
            else:
                incident = Incident(
                    charger_id=snapshot.charger_id,
                    source_health_snapshot_id=snapshot.id,
                    severity=snapshot.risk_level,
                    title=f"Critical charger health detected for {snapshot.charger_id}",
                    description=snapshot.recommendation_text,
                )
                self.repository.add_incident(incident)
                domain_events.extend(["IncidentCreated", "OperationsTeamNotified"])

        return MaintenanceDecisionResponse(
            recommendation=recommendation,
            incident=incident,
            domain_events=domain_events,
        )
