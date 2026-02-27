# -*- coding: utf-8 -*-
"""
Движок построения графа рисков для owned-активов.
Оценивает связи между активами и потенциальными угрозами (без привязки к персонам).
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class AssetRiskGraph:
    """
    Управляет графом активов и их рисков.
    """

    def __init__(self):
        self.nodes = set()
        self.edges = []

    def add_asset(self, asset_id: str, asset_type: str, risk_score: float = 0.0):
        """Добавляет узел актива."""
        self.nodes.add((asset_id, asset_type, risk_score))

    def add_risk_relation(self, source_id: str, target_id: str, risk_type: str, weight: float = 1.0):
        """Добавляет связь, отражающую риск между активами."""
        self.edges.append(
            {
                "source": source_id,
                "target": target_id,
                "risk_type": risk_type,
                "weight": weight,
            }
        )

    def get_risk_profile(self, asset_id: str) -> Dict:
        """
        Возвращает подграф рисков для указанного актива.
        """
        profile = {"nodes": [], "edges": []}
        for edge in self.edges:
            if edge["source"] == asset_id or edge["target"] == asset_id:
                profile["edges"].append(edge)
        nodes_set = set()
        for edge in profile["edges"]:
            nodes_set.add(edge["source"])
            nodes_set.add(edge["target"])

        for node in nodes_set:
            for stored_node in self.nodes:
                if stored_node[0] == node:
                    profile["nodes"].append(
                        {
                            "id": stored_node[0],
                            "type": stored_node[1],
                            "risk_score": stored_node[2],
                        }
                    )
                    break
        return profile


asset_risk_graph = AssetRiskGraph()


async def enrich_asset_risk(owned_domains: List[str]):
    """
    Обогащает граф рисками на основе публичных данных.
    """
    from app.osint.public_data_collector import PublicAssetDataCollector

    collector = PublicAssetDataCollector()
    indicators = await collector.collect_asset_indicators(owned_domains)

    for indicator in indicators:
        domain = indicator["domain"]
        asset_risk_graph.add_asset(domain, "DOMAIN", risk_score=0.5)

    if not owned_domains:
        return {"nodes": [], "edges": []}
    return asset_risk_graph.get_risk_profile(owned_domains[0])
