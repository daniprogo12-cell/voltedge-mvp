from fastapi import FastAPI

from health_context.routes import router

app = FastAPI(title="VoltEdge Health Service")
app.include_router(router)
