# -*- coding: utf-8 -*-
"""Пример асинхронного обогащения с записью связей в Neo4j."""

from app.analytics.relation_engine import graph_db


async def process_object_data(object_id: str, related_data: dict):
    await graph_db.add_relation(
        source_id=object_id,
        source_label="OBJECT",
        target_id=related_data["id"],
        target_label=related_data["type"],
        relation_type=related_data["relation"],
        weight=related_data.get("weight", 1.0),
    )
