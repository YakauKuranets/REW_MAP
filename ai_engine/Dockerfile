FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/ai_engine

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev build-essential cmake libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY ai_engine /srv/ai_engine

RUN python3 -m pip install --upgrade pip && \
    pip install -r /srv/ai_engine/requirements.txt

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
