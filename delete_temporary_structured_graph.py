from neo4j import GraphDatabase

def run_structured_graph_cleanup(
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "22222222",
    database: str = "structured-graph",
) -> None:
    """
    cleans the temporary structured-graph
    """
    cypher = "MATCH (n) DETACH DELETE n;"
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as s:
            s.run(cypher)
    finally:
        driver.close()
