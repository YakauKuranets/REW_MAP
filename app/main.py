import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.alerting.routes import router as alerting_router
from app.diagnostics.routes import router as diagnostics_router
from app.osint.routes import router as osint_router
from app.threat_intel.routes import router as threat_intel_router
from app.tracker.routes import router as tracker_router

logger = logging.getLogger(__name__)


# OpenTelemetry setup
JAEGER_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger-collector:4317")
resource = Resource.create({"service.name": "playe-api-gateway"})
tracer_provider = TracerProvider(resource=resource)
otlp_exporter = OTLPSpanExporter(endpoint=JAEGER_ENDPOINT, insecure=True)
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(tracer_provider)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.warning("[SYSTEM] Инициализация PLAYE STUDIO PRO v5.0 (FastAPI Core)")
    yield
    logger.warning("[SYSTEM] Остановка систем...")


app = FastAPI(
    title="PLAYE CTI COMMAND CENTER",
    description="Military-Grade API for Threat Intelligence & Field Operations",
    version="5.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tracker_router, prefix="/api/v1/tracker", tags=["Field Tracker"])
app.include_router(diagnostics_router, prefix="/api/v1/diagnostics", tags=["Cyber-Physical Scanners"])
app.include_router(threat_intel_router, prefix="/api/v1/threat_intel", tags=["OSINT & Attribution Kraken"])
app.include_router(alerting_router, prefix="/api/v1/alerting", tags=["SOAR & Alerts"])
app.include_router(osint_router, prefix="/api/v1/osint", tags=["OSINT"])

# Automatic tracing
FastAPIInstrumentor.instrument_app(app)
HTTPXInstrumentor().instrument()


@app.get("/health", tags=["System"])
async def health_check():
    """Проверка состояния орбитального ядра"""
    return {"status": "online", "core": "FastAPI"}
