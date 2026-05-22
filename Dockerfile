FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared ./shared
COPY telemetry_context ./telemetry_context
COPY health_context ./health_context
COPY maintenance_context ./maintenance_context
COPY dashboard ./dashboard

RUN mkdir -p /app/data
