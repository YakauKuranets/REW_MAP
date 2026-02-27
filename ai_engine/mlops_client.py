import logging
import os

import mlflow

logger = logging.getLogger(__name__)

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow-service:5000")
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)


class AIOperativeBrain:
    def __init__(self, model_name="ThreatPredictor"):
        self.model_name = model_name
        self.model = None
        self.version = "heuristic_fallback"

    def sync_production_model(self):
        """Load latest Production model from MLflow registry."""
        logger.info("[MLOps] Синхронизация нейроядра '%s' с MLflow...", self.model_name)
        try:
            model_uri = f"models:/{self.model_name}/Production"
            self.model = mlflow.pyfunc.load_model(model_uri)
            logger.critical(
                "[MLOps] Боевая ИИ-модель '%s' успешно загружена и переведена в активный режим!",
                self.model_name,
            )
            self.version = "production_ml"
        except Exception as e:
            logger.warning("[MLOps] Боевая модель не найдена. Переход на базовые эвристики. Ошибка: %s", e)
            self.model = None
            self.version = "heuristic_fallback"

    async def predict_threat(self, payload: dict) -> dict:
        """Prediction API used by FastAPI handlers."""
        if self.model:
            prediction = self.model.predict(payload)
            return {"confidence": float(prediction), "source": "mlflow_neural"}
        return {"confidence": 0.85, "source": "static_heuristics"}


threat_brain = AIOperativeBrain()
