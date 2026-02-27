# -*- coding: utf-8 -*-
"""
Движок для построения и хранения графа связей между объектами.
Использует Neo4j в качестве персистентного хранилища.
"""

import logging
import os

from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://db_graph:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "graph_secure_pass")


class GraphRelationDriver:
    """
    Асинхронный драйвер для работы с Neo4j.
    Позволяет добавлять связи между объектами и извлекать связанные данные.
    """

    def __init__(self, uri: str, user: str, password: str):
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self):
        await self.driver.close()

    async def add_relation(
        self,
        source_id: str,
        source_label: str,
        target_id: str,
        target_label: str,
        relation_type: str,
        weight: float = 1.0,
        properties: dict | None = None,
    ) -> None:
        """
        Добавляет или обновляет связь между двумя объектами.
        Использует MERGE для предотвращения дублирования.
        """
        query = f"""
        MERGE (a:{source_label} {{id: $source_id}})
        MERGE (b:{target_label} {{id: $target_id}})
        MERGE (a)-[r:{relation_type}]->(b)
        SET r.weight = $weight, r.last_seen = timestamp()
        SET r += $properties
        """
        async with self.driver.session() as session:
            await session.run(
                query,
                source_id=source_id,
                target_id=target_id,
                weight=weight,
                properties=properties or {},
            )
            logger.debug(
                "[GRAPH] Связь записана: [%s:%s] -(%s)-> [%s:%s]",
                source_label,
                source_id,
                relation_type,
                target_label,
                target_id,
            )

    async def get_object_relations(self, object_id: str) -> dict:
        """
        Извлекает связи объекта на глубину до 2 шагов.
        Возвращает структуру для визуализации.
        """
        query = """
        MATCH (a {id: $object_id})-[r]-(connected)
        RETURN labels(connected)[0] AS type, connected.id AS entity, type(r) AS relation
        """
        result_data = {"object_id": object_id, "connections": []}
        async with self.driver.session() as session:
            result = await session.run(query, object_id=object_id)
            records = await result.data()
            for record in records:
                result_data["connections"].append(
                    {
                        "entity": record["entity"],
                        "type": record["type"],
                        "relation": record["relation"],
                    }
                )
        return result_data


graph_db = GraphRelationDriver(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
