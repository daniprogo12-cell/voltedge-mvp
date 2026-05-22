from fastapi import FastAPI

from telemetry_context.routes import router

app = FastAPI(title="VoltEdge Telemetry Service")
app.include_router(router)
