# VoltEdge MVP - Microservice Architecture

Projektet er struktureret efter tre DDD bounded contexts og et separat dashboard til visualisering.

## Struktur



## Services

- Telemetry Service: http://localhost:8001
- Health Service: http://localhost:8002
- Maintenance Service: http://localhost:8003
- Dashboard visualisering: http://localhost:8004/dashboard

## Kør projektet

```powershell
docker compose up --build
```

## Test i Postman

POST `http://localhost:8001/telemetry`

```json
{
  "charger_id": "CH-008",
  "status": "offline",
  "power_kw": 0,
  "error_code": "E-17",
  "heartbeat": false
}
```

Flowet er:

```text
Telemetry Service -> Health Service -> Maintenance Service -> Dashboard
```

Dashboardet er ikke et DDD bounded context. Det er kun et visualiseringslag.
