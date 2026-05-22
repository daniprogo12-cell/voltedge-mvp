# Arkitektur

MVP'en er implementeret som en microservice-arkitektur med tre domæne-services:

1. Telemetry Service
2. Health Service
3. Maintenance Service

Dashboardet er ikke et bounded context. Det fungerer som visualisering/read model og henter data fra de tre services via HTTP.

## Data ownership

- Telemetry Service ejer `telemetry_store.json`
- Health Service ejer `health_store.json`
- Maintenance Service ejer `maintenance_store.json`

`Incident` er en del af Maintenance Context og gemmes derfor i `maintenance_store.json`.
