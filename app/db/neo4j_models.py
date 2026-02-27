# app/db/neo4j_models.py
from app.analytics.relation_engine import graph_db


class Neo4jModel:
    @staticmethod
    async def init_constraints():
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (a:THREAT_ACTOR) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:DEVICE_FINGERPRINT) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (g:GEO_REGION) REQUIRE g.id IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (d:DEVICE_FINGERPRINT) ON (d.model_hash)",
        ]
        async with graph_db.driver.session() as neo4j_session:
            for query in queries:
                await neo4j_session.run(query)
