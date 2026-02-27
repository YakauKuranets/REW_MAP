# -*- coding: utf-8 -*-
"""Compatibility layer delegating graph operations to app.analytics.relation_engine."""

from __future__ import annotations

import hashlib
import random
from typing import Any

from app.analytics.relation_engine import graph_db
from app.osint.image_validator import decrypt_metadata, validate_image_integrity


class KrakenDBAdapter:
    """Back-compat adapter for old routes expecting get_actor_profile()."""

    async def add_evidence(
        self,
        source_id: str,
        source_label: str,
        target_id: str,
        target_label: str,
        rel_type: str,
        weight: float = 1.0,
        properties: dict | None = None,
    ):
        await graph_db.add_relation(
            source_id=source_id,
            source_label=source_label,
            target_id=target_id,
            target_label=target_label,
            relation_type=rel_type,
            weight=weight,
            properties=properties,
        )

    async def get_actor_profile(self, alias: str) -> dict[str, Any]:
        profile = await graph_db.get_object_relations(alias)
        return {
            "alias": alias,
            "connections": profile.get("connections", []),
        }


kraken_db = KrakenDBAdapter()


async def enrich_actor_profile(alias: str, email: str | None = None) -> dict[str, Any]:
    """Legacy enrichment entrypoint writing data through Neo4j relation engine."""
    if email:
        await kraken_db.add_evidence(alias, "THREAT_ACTOR", email, "EMAIL", "HAS_EMAIL", weight=0.9)
    return await kraken_db.get_actor_profile(alias)


async def process_actor_image(alias: str, image_path: str):
    """
    Обрабатывает изображение, предположительно связанное с объектом интереса.
    Использует валидатор изображений для получения метаданных.
    """
    validation_result = validate_image_integrity(image_path)

    if not validation_result["valid"]:
        return await kraken_db.get_actor_profile(alias)

    metadata = decrypt_metadata(validation_result["metadata"])

    if "device" in metadata:
        device_hash = hashlib.sha256(str(metadata["device"]).encode()).hexdigest()[:16]
        await kraken_db.add_evidence(
            source_id=alias,
            source_label="THREAT_ACTOR",
            target_id=device_hash,
            target_label="DEVICE_FINGERPRINT",
            rel_type="ASSOCIATED_WITH",
            weight=0.9,
            properties={
                "model_hash": device_hash,
                "encrypted_model": validation_result["metadata"].get("device", ""),
            },
        )

    if "gps" in metadata and isinstance(metadata["gps"], dict):
        gps = metadata["gps"]
        lat_rounded = round(float(gps["lat"]), 2)
        lon_rounded = round(float(gps["lon"]), 2)
        geo_region = f"{lat_rounded},{lon_rounded}"

        encrypted_gps = validation_result["metadata"].get("gps", "")

        await kraken_db.add_evidence(
            source_id=alias,
            source_label="THREAT_ACTOR",
            target_id=geo_region,
            target_label="GEO_REGION",
            rel_type="VISITED",
            weight=0.8,
            properties={"exact_coordinates_encrypted": encrypted_gps},
        )

    await _inject_noise_nodes(alias)

    return await kraken_db.get_actor_profile(alias)


async def _inject_noise_nodes(alias: str):
    """
    Внедряет в граф случайные фиктивные связи.
    """
    fake_devices = ["Canon EOS 5D", "iPhone 12", "Samsung Galaxy S21", "Nikon D850", "Google Pixel 6"]
    fake_regions = ["55.75,37.61", "40.71,-74.00", "34.05,-118.24", "51.50,-0.12", "35.68,139.76"]

    for _ in range(random.randint(2, 3)):
        fake_device = random.choice(fake_devices)
        device_hash = hashlib.sha256(fake_device.encode()).hexdigest()[:16]
        await kraken_db.add_evidence(
            source_id=alias,
            source_label="THREAT_ACTOR",
            target_id=device_hash,
            target_label="DEVICE_FINGERPRINT",
            rel_type="ASSOCIATED_WITH",
            weight=0.1,
            properties={"fake": True},
        )

    for _ in range(random.randint(1, 2)):
        fake_region = random.choice(fake_regions)
        await kraken_db.add_evidence(
            source_id=alias,
            source_label="THREAT_ACTOR",
            target_id=fake_region,
            target_label="GEO_REGION",
            rel_type="VISITED",
            weight=0.1,
            properties={"fake": True},
        )


async def process_new_intel(raw_intel: dict[str, Any]) -> dict[str, Any]:
    """Legacy ingest API used by forum monitor."""
    alias = raw_intel.get("author", "unknown_actor")

    wallet = raw_intel.get("btc_wallet")
    if wallet:
        await kraken_db.add_evidence(alias, "THREAT_ACTOR", wallet, "CRYPTO_WALLET", "RECEIVED_FUNDS")

    ip_address = raw_intel.get("ip")
    if ip_address:
        await kraken_db.add_evidence(alias, "THREAT_ACTOR", ip_address, "IP_ADDRESS", "USED_INFRA")

    pgp_key = raw_intel.get("pgp_key")
    if pgp_key:
        await kraken_db.add_evidence(alias, "THREAT_ACTOR", pgp_key, "PGP_KEY", "SIGNED_WITH")

    if alias != "unknown_actor" and raw_intel.get("email"):
        await kraken_db.add_evidence(alias, "THREAT_ACTOR", raw_intel["email"], "EMAIL", "HAS_EMAIL", weight=0.9)

    return await kraken_db.get_actor_profile(alias)
