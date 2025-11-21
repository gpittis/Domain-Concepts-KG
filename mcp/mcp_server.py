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
# Timeout settings
QUERY_TIMEOUT_SECONDS = 60  # Max time per Cypher query
APP_TOOL_TIMEOUT_SECONDS = 10  # General timeout per tool execution

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
    return max(1, min(v, 2000))

def _query_top_related_concepts(limit: int = 1000) -> List[Dict[str, Any]]:
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
    lim = _clamp_limit(limit, 1000)

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

def _query_top_concepts(limit: int = 1000) -> List[Dict[str, Any]]:
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
    lim = _clamp_limit(limit, 1000)

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
    Return neighbors Concepts around the given Concept (domain_name) in the user prompt ordered by weight DESC

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

def _query_neighbors_multi_level(
    domain_name: str,
    max_level: int = 1,
    per_level_limit: int = 100,
    global_limit: int = 1000,
) -> List[Dict[str, Any]]:
    
    """
    Multi-level exploration around a seed domain_name, implemented by repeatedly calling the Level-1 helper.

    IMPORTANT:
      - At each level, for each seed node, we fetch its top-Level-1 neighbors,
        sorted by edge.final_weight (using _query_neighbors_for_domain_provided_by_user).

    Returns rows with:
      - domain_name : the seed of this hop (local seed at this level)
      - neighbor    : the neighbor discovered from that seed
      - level       : hop distance from the root domain_name (1..max_level)
      - final_weight: weight of the edge (seed -> neighbor)
    """

    # We use step-by-step Level-1 queries (from level 0 up to max_level), instead of one big Cypher query. 

    # One large "multi-hop" query can easily blow up in size, 
    # because Neo4j tries to explore too many paths at once. 
    # On big or dense graphs this often causes memory errors (dbms.memory.transaction.total.max error).

    # With the step-by-step approach:
    # - each Neo4j query stays small and safe,
    # - we limit branching with per_level_limit and global_limit,
    # - and the expensive logic runs in Python script instead of Neo4j KG, so the database never runs out of memory.

    # Normalize / clamp parameters
    max_level = max(1, int(max_level))
    per_level_limit = max(1, min(int(per_level_limit), 500))
    global_limit = max(1, min(int(global_limit), 5000))

    # Level-0 frontier = only the original user-provided domain.
    # The frontier is the queue of nodes whose Level-1 neighbors we will explore at the next level.
    frontier = [{
        "name": domain_name, # seed node name for the next hop
        "level": 0, # 0 hops away from the root
    }]

    # Collected results across ALL levels (1..max_level)
    rows: List[Dict[str, Any]] = []

    # Multi-level loop:
    # level-1 → explore direct (Level-1) neighbors of the original root domain provided by user.
    # level-2 → explore direct neighbors of all nodes found at level 1
    # level-3 → explore direct neighbors of all nodes found at level 2
    # level-4 → ... etc.

    # For example:
    # max_level = 1 → returns only level-1 neighbors of the root domain.
    # max_level = 2 → returns both level-1 and level-2 neighbors of the root domain.
    # max_level = 3 → returns level-1, level-2, and level-3 neighbors of the root domain.
    for level in range(1, max_level + 1):

        # If there are no more nodes to expand (frontier is empty),
        # OR we have already collected at least global_limit results,
        # we stop the multi-level search early.
        if not frontier or len(rows) >= global_limit:
            break
        
        # Seeds for the next level will be stored here
        new_frontier: List[Dict[str, Any]] = []

        # For every seed node in the current frontier, perform a simple Level-1 neighbors query
        for node in frontier:

            # Safety check: if we've already hit global_limit, we stop expanding further.
            if len(rows) >= global_limit:
                break
            
            # The "seed" concept whose direct neighbors we are about to query.
            seed_name = node["name"]

            # Fetch the top Level-1 neighbors for this seed.
            neighbors = _query_neighbors_for_domain_provided_by_user(
                domain_name=seed_name,
                limit=per_level_limit,
            )

            # For each neighbor returned by the Level-1 helper function,
            # we create a record that describes the (seed -> neighbor) pair
            # at the current level of the multi-level search.
            for n in neighbors:

                # Safety check
                if len(rows) >= global_limit:
                    break
                
                # Neighbor node name (e.g. "laser", "map", "order", ...)
                neigh_name = n["neighbor"]

                # edge weight for (seed_name -> neighbor) pair
                edge_weight = float(n["final_weight"] or 0.0)

                # Append result row
                rows.append({
                    "domain_name": seed_name, # seed for this hop
                    "neighbor": neigh_name, # direct neighbor of this seed
                    "level": level, # hop distance from the root domain concept provided by user
                    "final_weight": edge_weight,  # final weight of the pair
                })

                # This neighbor becomes a seed for the next level
                new_frontier.append({
                    "name": neigh_name,
                    "level": level,
                })

        # Replace frontier with newly collected seeds for the next hop
        frontier = new_frontier

    # Optional sorting: by level ASC, final_weight DESC, neighbor ASC
    rows.sort(key=lambda r: (r["level"], -r["final_weight"], r["neighbor"]))

    # Return up to global_limit items (already enforced earlier).
    # (so the slicing is optional)
    return rows[:global_limit]

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
def neo4j_top_related_concepts(limit: int = 1000) -> Dict[str, Any]:
    """
    Executes "_query_top_related_concepts" function and finds the top "weighted" relationships.
    In other words, finds the TOP RELATED Concepts.
    """

    # the "rows" list contains the top "weighted" relationships
    rows = _query_top_related_concepts(limit)

    # Build the response payload
    return {
        "edges": rows,
        "limit": _clamp_limit(limit, 1000),
    }

# tool 2
@mcp.tool(description=(
        "Return top concepts ordered by count desc. "
        "Args: limit (int, default 1000)."
    ))
def neo4j_top_concepts(limit: int = 1000) -> Dict[str, Any]:
    """
    Executes "_query_top_concepts" function and finds the most frequent Concepts.
    """

    # the "rows" list contains the most frequent Concepts/most dominant Concepts
    rows = _query_top_concepts(limit)

    # Build the response payload
    return {
        "nodes": rows,
        "limit": _clamp_limit(limit, 1000),
    }

# tool 3 
@mcp.tool(description=(
    "Return multi-level neighbors for a given Concept (domain_name) in the Neo4j KG.\n"
    "Args:\n"
    "  - domain_name (str, required): seed Concept name (root).\n"
    "  - max_level (int, default 1): how many hops away to explore "
    "        (1 = level-1 only, 2 = level-1 + level-2, 3 = level-1 + level-2 + level-3 etc).\n"
    "  - per_level_limit (int, default 100): max Level-1 neighbors per seed per level.\n"
    "  - global_limit (int, default 1000): max total (all levels) pairs to return.\n"
    "The LLM should start with max_level=1 and increase it only when broader context is needed."
    "The search is level-by-level: each level uses only direct (Level-1) neighbors of the previous level."
    "Weights are local to each hop (no cumulative path weights)."
))
def neo4j_neighbors_for_domain(
    domain_name: str,
    max_level: int = 1,
    per_level_limit: int = 100,
    global_limit: int = 1000,
) -> Dict[str, Any]:
    
    # Run the multi-level neighbor search helper
    rows = _query_neighbors_multi_level(
        domain_name=domain_name,
        max_level=max_level,
        per_level_limit=per_level_limit,
        global_limit=global_limit,
    )
    return {
        "domain_name": domain_name,  # root Concept
        "max_level": max_level, # depth explored
        "per_level_limit": per_level_limit, # max neighbors per seed per level
        "global_limit": global_limit, # max total result rows
        "neighbors": rows, # list of {domain_name, neighbor, level, final_weight} 
    }

if __name__ == "__main__":
    # Run the MCP server.
    mcp.run()
