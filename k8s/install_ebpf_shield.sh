#!/bin/bash
set -euo pipefail

echo "[eBPF] Установка Cilium CNI и Hubble..."
helm repo add cilium https://helm.cilium.io/
helm repo update
helm install cilium cilium/cilium \
    --namespace kube-system \
    --set hubble.relay.enabled=true \
    --set hubble.ui.enabled=true

echo "[eBPF] Установка Tetragon (Security Enforcement)..."
helm repo add tetragon https://helm.cilium.io
helm repo update
helm install tetragon tetragon/tetragon \
    --namespace kube-system

echo "[eBPF] Инфраструктура Ring 0 развернута. Ожидание запуска подов..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=tetragon -n kube-system --timeout=90s
