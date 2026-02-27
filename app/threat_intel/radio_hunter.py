"""Radio hunter anomaly detector based on Neo4j graph signals."""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


class RadioHunterEngine:
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://playe-neo4j-cluster:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self) -> None:
        self.driver.close()

    def find_anomalous_towers(self) -> List[Dict]:
        query = """
        MATCH (agent:Operative)-[r:INTERCEPTED_SIGNAL]->(tower:CellNode)
        WHERE tower.signal_strength > 90 AND tower.registered_provider = 'UNKNOWN'
        WITH tower, count(DISTINCT agent) as hunter_count, collect(r.timestamp) as timestamps
        WHERE hunter_count >= 3
        RETURN tower.id as tower_id,
               tower.location_lat as lat,
               tower.location_lon as lon,
               tower.mac_address as mac,
               tower.signal_strength as signal,
               hunter_count
        LIMIT 10
        """
        with self.driver.session() as session:
            result = session.run(query)
            suspects = [record.data() for record in result]
            if suspects:
                logger.warning("[RADIO_HUNTER] Обнаружено %s подозрительных узлов", len(suspects))
            else:
                logger.info("[RADIO_HUNTER] Аномальных узлов не найдено")
            return suspects

    def get_primary_target(self) -> Optional[Dict]:
        suspects = self.find_anomalous_towers()
        if not suspects:
            return None

        target = suspects[0]
        logger.warning(
            "[RADIO_HUNTER] Координаты цели переданы в Командный Центр: %s, %s",
            target.get("lat"),
            target.get("lon"),
        )
        return {
            "target_lat": target.get("lat"),
            "target_lon": target.get("lon"),
            "type": "Syndrome_Hardware",
        }


hunter_engine = RadioHunterEngine()
