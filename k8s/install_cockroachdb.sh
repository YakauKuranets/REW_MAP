#!/bin/bash
set -euo pipefail

echo "[NewSQL] Добавление репозитория CockroachDB..."
helm repo add cockroachdb https://charts.cockroachdb.com/
helm repo update

echo "[NewSQL] Развертывание распределенного кластера (3 узла)..."
helm install playe-db cockroachdb/cockroachdb \
    --namespace dutytracker \
    --set statefulset.replicas=3 \
    --set storage.persistentVolume.size=50Gi \
    --set tls.enabled=false

echo "[NewSQL] Ожидание инициализации кластера..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=cockroachdb -n dutytracker --timeout=120s

echo "[NewSQL] Кластер готов. Доступ по порту 26257."
