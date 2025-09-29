import json
import itertools
from collections import defaultdict
from neo4j import GraphDatabase
import nltk
from nltk.stem.snowball import SnowballStemmer
from pathlib import Path

"""
knowledge_graph_define_json.py : Build a "knowledge graph" from a Neo4j structured graph created by static analysis.
"""

# ---------- CYPHER QUERIES ----------

# Retrieve all nodes that do not have REPO label and have a valid, non-synthetic name.
# 1. exclude REPO labeled nodes
# 2. require a non-NULL name
# 3. name must not be empty/whitespace
# 4. exclude synthetic names ('_ANON_')
# 5. return the label of the node (e.g., FILE, FUNCTION, CLASS) as kind property
# 6. return the raw name of the node to be tokenized/stemmed
# 7. return the node weight as float number
CYPHER_NODES = """
MATCH (n)
WHERE NOT 'REPO' IN labels(n)
  AND n.name IS NOT NULL
  AND trim(n.name) <> ''
  AND NOT n.name CONTAINS '_ANON_'
RETURN
  head(labels(n)) AS kind,
  n.name AS name,
  toFloat(n.weight) AS node_weight
"""

# Retrieve relationships between non-REPO nodes that have valid, non-synthetic names.
# 1. exclude REPO-labeled source nodes
# 2. exclude REPO-labeled target nodes
# 3. require non-NULL names on both ends (source + target nodes)
# 4. both node names must not be empty/whitespace
# 5. exclude synthetic names (source node)
# 6. exclude synthetic names (target node)
# 7. keep only relationships with final weight (optional because every relationship has final weight)
# 8. return raw name of source node (to tokenize/stem)
# 9. return raw name of target node (to tokenize/stem)
# 10. return relationship's final weight as float w
CYPHER_RELS = """
MATCH (u)-[r]->(v)
WHERE NOT 'REPO' IN labels(u)
  AND NOT 'REPO' IN labels(v)
  AND u.name IS NOT NULL AND v.name IS NOT NULL
  AND trim(u.name) <> '' AND trim(v.name) <> ''
  AND NOT u.name CONTAINS '_ANON_'
  AND NOT v.name CONTAINS '_ANON_'
  AND r.final_weight IS NOT NULL
RETURN
  u.name AS src_name,
  v.name AS dst_name,
  toFloat(r.final_weight) AS w
"""

# ---------- NLP task (only NLTK stemming) ----------

# Download a small NLTK resource if missing (safe no-op if already present)
nltk.download("wordnet", quiet=True)

# Create an English Snowball stemmer
_stemmer = SnowballStemmer("english")

def stemming_tokens(tokens):
    """Stem a list of tokens: lowercase, drop 1-char tokens, then apply stemming."""
    # lowercasing is optional because stopwords_filter does this conversion.
    # Dropping single-character tokens is optional because stopwords_filter already removes tokens with length < 3.
    # I added these 2 filters for safety.
    return [_stemmer.stem(t.lower()) for t in tokens if len(t) > 1]

def to_concepts(name: str) -> list[str]:
    """Split a node name on whitespace and stem each piece into concept tokens."""
    # 1. Split the node name into words on whitespace. 
    # (i.e. take a string and cut it into separate words(concepts) wherever there’s whitespace.)
    # 2. Send those words to stemming_tokens().

    # Example :
    # "render img" → ["render", "img"]
    tokens = name.strip().split()
    return stemming_tokens(tokens)

# ---------- HELPER ----------
# Return the pair in alphabetical order.
# So the pairs (a,b) and (b,a) are mapping to the same relationship.
def normalize_pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)

# ---------- knowledge_graph_definition function ----------
def knowledge_graph_definition(
    uri: str,
    user: str,
    password: str,
    database: str,
) -> dict:
    # Connect to Neo4j structured-graph and take rows for nodes and relationships.
    # Then close the driver.
    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session(database=database) as s:
        nodes_rows = [dict(r) for r in s.run(CYPHER_NODES)]
        rels_rows  = [dict(r) for r in s.run(CYPHER_RELS)]
    driver.close()

    node_counts = defaultdict(int) # token -> appearance count across node names
    edge_agg = {}

    # 1) Node-based co-existence
    for row in nodes_rows:  # iterate over every structured node row
        tokens = to_concepts(row["name"]) # split + stem the structured node name into concept tokens.
        if not tokens: # if no tokens, then skip this structured node
            continue
        node_weight = float(row.get("node_weight") or 0.0) # read the node's weight as float; default to 0.0 if missing/NULL

        # For every (possibly repeated) token that came from this structured node's name,
        # increment the per-token appearance counter (node_counts[t]).
        # Example: "render img render img" → both 'render' and 'img' have count = 2.
        for t in tokens:
            node_counts[t] += 1
        
        # If the structured node name contains at least two "distinct" tokens, create a co-existence relationship.
        if len(tokens) >= 2:

            # For each distinct token pair co-existing in the same structured node name,
            # add a co-existence contribution of 2 * node_weight to the (u, v) relationship’s final_weight.
            
            # Example : CLASS("render img") with CLASS_node_weight = 0.95,
            # contributes 2 * 0.95 = 1.90 to the relationship (img, render).
            # So i have : (img) -[relationship_final_weight += 1.90] -> (render)

            base_w = 2.0 * node_weight # node_weight = weight of the originating structured node.

            # Build co-existence edges from this structured node’s tokens.
            # sorted(set(tokens)) : unique tokens from this name, in stable order.
            # Duplicate tokens in the name do NOT create extra co-existence pairs. (They’re already counted in node_counts).
            # combinations(..., 2) → all distinct pairs (a, b) with a != b.
            for a, b in itertools.combinations(sorted(set(tokens)), 2):

                # canonicalize the token's names alphabetically so the edge is undirected and deduplicated globally.
                u, v = normalize_pair(a, b) 
                if u == v:   # skip self-loops
                    continue

                # edge_agg: a dict keyed by the alphabetically normalized pair (u, v),
                # with the value holding the aggregated edge fields (i.e. "final_weight" and "count" fields)
                # If an edge for (u, v) already exists, return its current aggregate (so we can add to it).
                # If not, return a fresh aggregate initialized with final_weight=0.0 and count=0.
                e = edge_agg.get((u, v), {"final_weight": 0.0, "count": 0})

                e["final_weight"] += base_w  # add this contribution’s weight to edge's final_weight
                e["count"] += 1   # record one more contribution 
                edge_agg[(u, v)] = e  # store the updated aggregate


    # 2) Relationship-based (Cartesian product)

    # Example : CLASS("render img") -[HAS_METHOD]-> METHOD("depth color") 
    
    # Su = to_concepts("render img") → ["render", "img"]
    # Sv = to_concepts("depth color") → ["depth", "color"]
    # Cartesian product (Su × Sv) :
    # (depth) -[RELATED_TO]-> (render)
    # (color) -[RELATED_TO]-> (render)
    # (depth) -[RELATED_TO]-> (img)
    # (color) -[RELATED_TO]-> (img)

    for row in rels_rows: # iterate over every structured relationship row
        Su = to_concepts(row["src_name"]) # source node name -> tokens
        Sv = to_concepts(row["dst_name"]) # target node name -> tokens
        if not Su or not Sv:  # If either side (.i.e source + target node) produced no tokens, then skip this relationship.
            continue 
        w = float(row["w"] or 0.0) # relationship final_weight (default 0.0)
        if w <= 0: # optional check (every weight is positive)
            continue
        for a in Su:  # for each source token
            for b in Sv: # for each target token
                u, v = normalize_pair(a, b) # normalize pair alphabetically
                if u == v:   # skip self-loops
                    continue

                # We do the same as above.
                e = edge_agg.get((u, v), {"final_weight": 0.0, "count": 0})
                e["final_weight"] += w
                e["count"] += 1
                edge_agg[(u, v)] = e

    # 3) JSON CREATION
    nodes_out = [{"type": "CONCEPT", "name": t, "count": c} for t, c in sorted(node_counts.items())]
    rels_out = [
        {"type": "RELATED_TO", "from": u, "to": v, "final_weight": round(d["final_weight"], 6), "count": d["count"]}
        for (u, v), d in sorted(edge_agg.items())
    ]

    # 4) return the knowledge graph json
    return {"nodes": nodes_out, "relationships": rels_out}

# Implement wrapper for the knowledge_graph_definition function
# We call this wrapper from api.
def run_kg_builder_from_structured_graph(
    output_path: str,
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "11111111",
    database: str = "structured-graph",
) -> Path:
    """
    Build the Knowledge Graph from the structured graph and WRITE it to JSON at output_path.
    Returns the Path to the written file.
    """
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    kg_json = knowledge_graph_definition(uri=uri, user=user, password=password, database=database)

    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(kg_json, f, ensure_ascii=False, indent=2)

    print(f"[DONE] KNOWLEDGE GRAPH JSON: {out_p}")
    print(f"KNOWLEDGE GRAPH JSON={out_p}")
    return out_p