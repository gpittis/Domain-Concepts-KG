"""
MCP Server that exposes 2 Neo4j tools:
1) neo4j_top_related_concepts  (finds edges: a-[:RELATED_TO]->b)
2) neo4j_top_concepts          (finds nodes)

Requirements :
pip install fastmcp "neo4j=5.28.2"
"""

# import json
from typing import List, Dict, Any

from neo4j import GraphDatabase

# FastMCP : high-level framework for building MCP servers/clients
# from mcp.server.fastmcp import FastMCP
from fastmcp import FastMCP

# -------------------------
# Neo4j connection settings
# -------------------------
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "22222222"
NEO4J_DATABASE = "knowledge-graph"
DEFAULT_LIMIT_NEIGHBORS = 200
DEFAULT_MIN_WEIGHT = 0.3
DEFAULT_MIN_COUNT = 1
# Timeout settings
QUERY_TIMEOUT_SECONDS = 60  # Max time per Cypher query
APP_TOOL_TIMEOUT_SECONDS = 10  # General timeout per tool execution

# Result limits (How many ROWS. In other words, how many nodes/edges)
DEFAULT_LIMIT_EDGES = 1000
DEFAULT_LIMIT_NODES = 1000
MAX_LIMIT = 2000

# ----------------------------
# Neo4j driver initialization
# ----------------------------
_driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
)

def _clamp_limit(value: int, default_value: int) -> int:
    """
    Ensures the provided limit value stays within [1, MAX_LIMIT].
    If invalid, fall back to a default.
    """
    try:
        v = int(value)
    except Exception:
        v = default_value
    return max(1, min(v, MAX_LIMIT))

def _query_top_related_concepts(limit: int = DEFAULT_LIMIT_EDGES) -> List[Dict[str, Any]]:
    """
    Query the top "weighted" relationships between Concepts(nodes), ordered by "final_weight" (descending).

    Parameters
    ----------
    limit : Max number of edges/relationships to return. Clamped to [1, MAX_LIMIT].

    Returns
    -------
    A list of dicts with keys:
        - "source":  source concept name (a.name)
        - "target":  target concept name (b.name)
        - "weight":  relationship's weight (r.final_weight)
        - "count" :  relationship's count (r.count)
    """

    # The Cypher Query that finds and returns the TOP "limit" relationships between Concepts.
    cypher = """
    MATCH (a:Concept)-[r:RELATED_TO]->(b:Concept)
    RETURN a.name AS Source,
           b.name AS Target,
           r.final_weight AS Weight,
           r.count AS Count
    ORDER BY r.final_weight DESC
    LIMIT $limit
    """

    # Ensure the provided limit stays within safe bounds
    lim = _clamp_limit(limit, DEFAULT_LIMIT_EDGES)

    # Open a session to the Neo4j database and run the Cypher Query. 
    with _driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(cypher, limit=lim, timeout=QUERY_TIMEOUT_SECONDS)

        # Convert the Neo4j result to a List of Dicts.
        # Every Dict contains the information of 1 edge.
        rows = []
        for rec in result:
            rows.append({
                "source": rec["Source"], # get the Source concept name from the query result row
                "target": rec["Target"], # get the Target concept name from the query result row
                "weight": rec["Weight"], # get the Weight of the relationship from the query result row
                "count": rec["Count"],   # get the Count of the relationship from the query result row
            })
        return rows

def _query_top_concepts(limit: int = DEFAULT_LIMIT_NODES) -> List[Dict[str, Any]]:
    """
    Return the most frequent Concepts(nodes) ordered by their "count" property (descending).

    Parameters
    ----------
    limit : Max number of concepts/nodes to return. Clamped to [1, MAX_LIMIT].

    Returns
    -------
    A list of dicts with keys :
        - "concept": concept name (n.name)
        - "count":   the count of concept (n.count)
    """

    # The Cypher Query that finds and returns the most frequent "limit" Concepts.
    cypher = """
    MATCH (n:Concept)
    RETURN n.name AS Concept, n.count AS Count
    ORDER BY Count DESC
    LIMIT $limit
    """

    # Keep the "limit" within safe bounds
    lim = _clamp_limit(limit, DEFAULT_LIMIT_NODES)

    # Open a session to the Neo4j database and run the Cypher Query.
    with _driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(cypher, limit=lim, timeout=QUERY_TIMEOUT_SECONDS)

        # Convert the Neo4j result to a List of Dicts.
        # Every Dict contains the information of 1 Concept.
        rows = []
        for rec in result:
            rows.append({
                "concept": rec["Concept"], # get the Concept/node name from the query result row
                "count": rec["Count"], # get the Count of the Concept/node from the query result row
            })
        return rows

def _query_neighbors_for_domain_provided_by_user(
    domain_name: str,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    Return neighbors Concepts around the given Concept (domain_name) in the user prompt, filtered by:
      - relationship weight >= min_weight
      - neighbor count   >= min_count
    Ordered by weight DESC, relationship count DESC, neighbor name ASC.

    Parameters
    ----------
    domain_name : str
        The name of the seed Concept node (the domain provided by the user).
    limit : int
        Maximum rows to return (clamped to [1, MAX_LIMIT]).

    Returns
    -------
    List[Dict[str, Any]]
        Each dict has:
        - "domain_name"    : the seed node name
        - "neighbor"       : neighbor node name
        - "final_weight"   : relationship weight
    """

    # Clamp basic inputs (server-side safety, even if the client also clamps)
    lim = _clamp_limit(limit, 200)  # default 200 rows in result

    # Cypher: use 'seed' as the variable name for the domain node
    cypher = """
    MATCH (seed:Concept {name: $domain_name})-[r:RELATED_TO]-(neighbor:Concept)
    RETURN seed.name      AS domain_name,
           neighbor.name  AS neighbor,
           r.final_weight AS final_weight
    ORDER BY final_weight DESC
    LIMIT $limit
    """

    with _driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(
            cypher,
            domain_name=domain_name,
            limit=lim,
            timeout=QUERY_TIMEOUT_SECONDS,
        )
        rows: List[Dict[str, Any]] = []
        for rec in result:
            rows.append({
                "domain_name":    rec["domain_name"],
                "neighbor":       rec["neighbor"],
                "final_weight":   rec["final_weight"]
            })
        return rows

def _query_neighbors_level2_for_domain(
    domain_name: str,
    top_first: int = 40,      # πόσους L1 κρατάμε
    limit_per_seed: int = 20  # πόσους L2 ανά L1
) -> List[Dict[str, Any]]:
    """
    Επιστρέφει μόνο LEVEL-2 neighbors:
      - Πρώτα βρίσκει τους top-<top_first> L1 γείτονες του seed (χωρίς φίλτρα).
      - Για κάθε L1, επιστρέφει τους top-<limit_per_seed> L2 γείτονές του.
    Επιστρέφει rows με:
      domain_name, seed_l1,
      neighbor, final_weight
    """
    # clamps
    tf = max(1, min(int(top_first), 200))
    lps = max(1, min(int(limit_per_seed), 200))

    cypher = """
    // Επιλογή top L1 γειτόνων (με βάση final_weight, rel_count, όνομα)
    MATCH (seed:Concept {name: $domain_name})-[r1:RELATED_TO]-(l1:Concept)
    WITH seed, l1, r1
    ORDER BY r1.final_weight DESC
    WITH seed, collect(l1)[0..$top_first] AS seeds1

    // Για κάθε L1, πάρε top L2 γείτονες
    UNWIND seeds1 AS s1
    MATCH (s1)-[r2:RELATED_TO]-(n2:Concept)
    WHERE n2 <> s1
    WITH seed, s1, n2, r2
    ORDER BY r2.final_weight DESC
    WITH seed, s1,
         collect({
           seed_l1: s1.name,
           seed_l1_count: s1.count,
           neighbor: n2.name,
           neighbor_count: n2.count,
           final_weight: r2.final_weight,
           rel_count: r2.count
         })[0..$limit_per_seed] AS top2
    UNWIND top2 AS t2
    RETURN
      seed.name            AS domain_name,
      t2.seed_l1           AS seed_l1,
      t2.neighbor          AS neighbor,
      t2.final_weight      AS final_weight
    """

    rows: List[Dict[str, Any]] = []
    with _driver.session(database=NEO4J_DATABASE or None) as session:
        result = session.run(cypher, 
                             domain_name=domain_name, 
                             top_first=tf, 
                             limit_per_seed = lps, 
                             timeout=QUERY_TIMEOUT_SECONDS)
        for rec in result:
            rows.append({
                "domain_name":    rec["domain_name"],
                "seed_l1":        rec["seed_l1"],
                "neighbor":       rec["neighbor"],
                "final_weight":   rec["final_weight"],
            })
    return rows

# --------------------------
# MCP server & exposed tools
# --------------------------

# Initialize an MCP server named "neo4j-graph-server".
# This server will expose the Neo4j query tools below to any MCP client.
mcp = FastMCP("neo4j-graph-server")

# tool 1
@mcp.tool(description=(
        "Return top RELATED_TO edges ordered by final_weight desc. "
        "Args: limit (int, default 1000)."
    ))
def neo4j_top_related_concepts(limit: int = DEFAULT_LIMIT_EDGES) -> Dict[str, Any]:
    """
    Executes "_query_top_related_concepts" function and finds the top "weighted" relationships.
    In other words, finds the TOP RELATED Concepts.
    """

    # the "rows" list contains the top "weighted" relationships
    rows = _query_top_related_concepts(limit)

    # Build the response payload
    return {
        "edges": rows,
        "limit": _clamp_limit(limit, DEFAULT_LIMIT_EDGES),
    }

# tool 2
@mcp.tool(description=(
        "Return top concepts ordered by count desc. "
        "Args: limit (int, default 1000)."
    ))
def neo4j_top_concepts(limit: int = DEFAULT_LIMIT_NODES) -> Dict[str, Any]:
    """
    Executes "_query_top_concepts" function and finds the most frequent Concepts.
    """

    # the "rows" list contains the most frequent Concepts/most dominant Concepts
    rows = _query_top_concepts(limit)

    # Build the response payload
    return {
        "nodes": rows,
        "limit": _clamp_limit(limit, DEFAULT_LIMIT_NODES),
    }

# tool 3
@mcp.tool(description=(
    "Return top neighbors for a given Concept(Domain Name provided by user) by final_weight (desc). "
    "Args: domain_name (str, required), limit (int, default 500)."
))
def neo4j_neighbors_for_domain(domain_name: str, limit: int = 500) -> Dict[str, Any]:
    """
    Executes the minimal neighbor query (no count/weight filters).
    Returns a JSON string with neighbors and the applied limit.
    """
    rows = _query_neighbors_for_domain_provided_by_user(domain_name=domain_name, limit=limit)
    return {
        "domain_name": domain_name,
        "limit": _clamp_limit(limit, 200),
        "neighbors": rows,
    }

# tool 4
@mcp.tool(description=(
    "Return only Level-2 neighbors for a given Concept (Domain Name provided by user). "
    "First selects the top_first Level-1 neighbors of the seed by final_weight (desc), "
    "then for each of them returns the top limit_per_seed Level-2 neighbors. "
    "Args: domain_name (str, required), top_first (int, default 100), limit_per_seed (int, default 20)."
))
def neo4j_neighbors_level2_for_domain(domain_name: str, top_first: int = 100, limit_per_seed: int = 20) -> Dict[str, Any]:
    """
    Executes the Level-2 neighbors query (no weight/count filters).
    Returns a JSON string with rows and the applied limits.
    """
    # optional server-side clamp (keeps numbers sane even if client doesn't)
    tf = max(1, min(int(top_first), 200))
    lps = max(1, min(int(limit_per_seed), 200))

    rows = _query_neighbors_level2_for_domain(
            domain_name=domain_name,
            top_first=tf,
            limit_per_seed=lps)
    return {
            "domain_name": domain_name,
            "top_first": tf,
            "limit_per_seed": lps,
            "records": rows,  # each record: domain_name, domain_count, seed_l1, seed_l1_count, neighbor, neighbor_count, final_weight, rel_count
        }

if __name__ == "__main__":
    # Run the MCP server.
    mcp.run()
