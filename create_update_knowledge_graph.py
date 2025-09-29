import json
from pathlib import Path
from neo4j import GraphDatabase

# ---------- create and update the neo4j Knowledge Graph ----------
def run_knowledge_graph_loader(
    input_json_path: str,
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "11111111",
    database: str = "knowledge-graph",
) -> tuple[int, int]:
    
    path = Path(input_json_path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])  # Extract list of node records (default: empty)
    rels  = data.get("relationships", [])  # Extract list of relationship records (default: empty)

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as s:
            # --- Constraint: Concept.name must be unique ---
            # Enforce uniqueness on Concept.name
            s.run("""
                CREATE CONSTRAINT IF NOT EXISTS
                FOR (c:Concept) REQUIRE c.name IS UNIQUE
            """)

            # ---- Nodes ----
            # Maintain exactly one Concept node per unique name (via MERGE).
            # When a Concept appears for the first time, initialize its occurrence counter from the incoming data.
            # When the same Concept appears again, increase its counter by the new incoming amount (accumulation).
            # Avoids duplicate nodes and stays safe to run many times.
            # Across loads, the count becomes the total number of appearances.
            s.run("""
                UNWIND $rows AS row
                MERGE (c:Concept {name: row.name})
                ON CREATE SET c.count = toInteger(row.count)
                ON MATCH  SET c.count = coalesce(c.count, 0) + toInteger(row.count)
            """, rows=nodes)

            # ---- Relationships ----
            # Maintain exactly one RELATED_TO edge per (from, to) concept pair.
            # On first appearance, initialize properties from the incoming row.
            # On subsequent appearances, accumulate count and final_weight (sum).
            # r.count = coalesce(r.count, 0) + toInteger(row.count) ---> accumulate count
            # r.final_weight = coalesce(r.final_weight, 0.0) + toFloat(row.final_weight) ---> accumulate final_weight
            if rels:
                s.run("""
                    UNWIND $rows AS row
                    MATCH (a:Concept {name: row.from})
                    MATCH (b:Concept {name: row.to})
                    MERGE (a)-[r:RELATED_TO]->(b)
                    ON CREATE SET
                        r.from_node_name = row.from,
                        r.to_node_name   = row.to,
                        r.count = toInteger(row.count),
                        r.final_weight = toFloat(row.final_weight)
                    ON MATCH SET
                        r.count = coalesce(r.count, 0) + toInteger(row.count),
                        r.final_weight = coalesce(r.final_weight, 0.0) + toFloat(row.final_weight),
                        r.from_node_name = row.from,
                        r.to_node_name   = row.to
                """, rows=rels)

            print(f"[OK] Loaded: nodes={len(nodes)}, relationships={len(rels)}")
            return len(nodes), len(rels)
    finally:
        driver.close()

