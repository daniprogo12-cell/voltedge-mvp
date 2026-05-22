from fastapi import FastAPI

from maintenance_context.routes import router

app = FastAPI(title="VoltEdge Maintenance Service")
app.include_router(router)
