from health_context.service import AnomalyDetectionService, HealthScoreCalculator
from shared.schemas import TelemetryReading


def test_faulted_charger_becomes_critical_high_risk():
    reading = TelemetryReading(
        charger_id="CH-001",
        status="faulted",
        power_kw=0,
        heartbeat=False,
        error_code="E-42",
    )

    snapshot = HealthScoreCalculator.calculate(reading, [reading])
    anomalies = AnomalyDetectionService.detect(reading, snapshot, [reading])

    assert snapshot.health_status == "critical"
    assert snapshot.risk_level == "high"
    assert snapshot.health_score == 5
    assert any(a.anomaly_type == "heartbeat_missing" for a in anomalies)


def test_healthy_charger_has_no_fault_indicators():
    reading = TelemetryReading(
        charger_id="CH-002",
        status="charging",
        power_kw=11.2,
        heartbeat=True,
    )

    snapshot = HealthScoreCalculator.calculate(reading, [reading])

    assert snapshot.health_status == "healthy"
    assert snapshot.risk_level == "low"
    assert snapshot.health_score == 100
    assert snapshot.fault_indicators == []
