from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="VoltEdge Dashboard / Visualisering")

TELEMETRY_API_URL = os.getenv("TELEMETRY_API_URL", "http://telemetry-api:8000")
HEALTH_API_URL = os.getenv("HEALTH_API_URL", "http://health-api:8000")
MAINTENANCE_API_URL = os.getenv("MAINTENANCE_API_URL", "http://maintenance-api:8000")
TEMPLATE_PATH = Path(__file__).parent / "templates" / "index.html"


async def get_json(url: str) -> Any:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def post_json(url: str, payload: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload or {})
        response.raise_for_status()
        return response.json()


async def delete_json(url: str) -> Any:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.delete(url)
        response.raise_for_status()
        return response.json()


@app.get("/")
def root():
    return {"service": "Dashboard / Visualisering", "dashboard": "/dashboard"}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return TEMPLATE_PATH.read_text(encoding="utf-8")


@app.get("/api/telemetry")
async def telemetry():
    return await get_json(f"{TELEMETRY_API_URL}/telemetry")


@app.get("/api/health/latest")
async def health_latest():
    return await get_json(f"{HEALTH_API_URL}/health/latest")


@app.get("/api/health")
async def health():
    return await get_json(f"{HEALTH_API_URL}/health")


@app.get("/api/anomalies")
async def anomalies():
    return await get_json(f"{HEALTH_API_URL}/anomalies")


@app.get("/api/recommendations")
async def recommendations():
    return await get_json(f"{MAINTENANCE_API_URL}/maintenance/recommendations")


@app.get("/api/incidents")
async def incidents(status: str | None = None):
    suffix = f"?status={status}" if status else ""
    return await get_json(f"{MAINTENANCE_API_URL}/maintenance/incidents{suffix}")


@app.post("/demo/seed")
async def seed():
    await reset_data()
    samples = [
        {"charger_id": "CH-001", "status": "available", "power_kw": 0, "heartbeat": True},
        {"charger_id": "CH-002", "status": "charging", "power_kw": 11.2, "heartbeat": True},
        {"charger_id": "CH-003", "status": "charging", "power_kw": 0, "heartbeat": True, "error_code": "E_POWER_01"},
        {"charger_id": "CH-004", "status": "offline", "power_kw": 0, "heartbeat": False, "error_code": "E_CONN_01"},
        {"charger_id": "CH-004", "status": "offline", "power_kw": 0, "heartbeat": False, "error_code": "E_CONN_01"},
        {"charger_id": "CH-004", "status": "faulted", "power_kw": 0, "heartbeat": False, "error_code": "E_CONN_01"},
    ]
    results = []
    for sample in samples:
        results.append(await post_json(f"{TELEMETRY_API_URL}/telemetry", sample))
    return {"inserted": len(results), "results": results}


@app.delete("/data/reset")
async def reset_data():
    return {
        "telemetry": await delete_json(f"{TELEMETRY_API_URL}/data/reset"),
        "health": await delete_json(f"{HEALTH_API_URL}/data/reset"),
        "maintenance": await delete_json(f"{MAINTENANCE_API_URL}/data/reset"),
    }
