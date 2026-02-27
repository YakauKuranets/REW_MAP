import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel

from ai.predictive_advisor import analyze_threat_context
from mlops_client import threat_brain
from vision.face_tracker import compare_faces_sync

logger = logging.getLogger(__name__)

resource = Resource.create({"service.name": "playe-ai-engine"})
tracer_provider = TracerProvider(resource=resource)
otlp_exporter = OTLPSpanExporter(
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger-collector:4317"),
    insecure=True,
)
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(tracer_provider)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threat_brain.sync_production_model()
    yield


app = FastAPI(title="PLAYE AI NEURAL ENGINE", version="1.0.0", lifespan=lifespan)

FastAPIInstrumentor.instrument_app(app)
HTTPXInstrumentor().instrument()


class ThreatContext(BaseModel):
    raw_text: str
    source: str


@app.post("/api/v1/analyze_threat")
async def analyze_threat(payload: ThreatContext):
    """LLM-анализ текста хакеров."""
    try:
        # attempt model inference from MLflow brain first
        ml_prediction = await threat_brain.predict_threat(
            {"raw_text": payload.raw_text, "source": payload.source}
        )
        result = await analyze_threat_context(payload.raw_text, payload.source)
        return {"status": "success", "analysis": result, "ml_prediction": ml_prediction, "model_version": threat_brain.version}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/v1/vision/compare_faces")
async def compare_faces(known_image: UploadFile = File(...), unknown_image: UploadFile = File(...)):
    """Тяжелая биометрия на GPU."""
    try:
        tmp_dir = Path("/tmp")
        known_path = tmp_dir / (known_image.filename or "known.jpg")
        unknown_path = tmp_dir / (unknown_image.filename or "unknown.jpg")

        known_path.write_bytes(await known_image.read())
        unknown_path.write_bytes(await unknown_image.read())

        match_confidence = compare_faces_sync(str(known_path), str(unknown_path))
        return {"status": "success", "confidence": match_confidence}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
