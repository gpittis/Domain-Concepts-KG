import math
from neo4j import GraphDatabase
from pyvis.network import Network

"""
PyVis is a Python wrapper (or binding) around the JavaScript library vis.js

vis.js : a Javascript library for interactive network visualizations in the browser.

PyVis : a Python layer that lets you create those visualizations without writing JavaScript.
"""

# pyvis.network : builds interactive network graphs in Python 
# and renders them in the browser using the JavaScript library vis.js

# ---- Single query: retrieve the top edges (by weight) and the counts of their endpoint nodes ----
Q_EDGES = """
MATCH (a:Concept)-[r:RELATED_TO]->(b:Concept)
RETURN a.name AS Source,
       b.name AS Target,
       r.final_weight AS Weight,
       r.count AS Count,
       a.count AS SourceCount,
       b.count AS TargetCount
ORDER BY r.final_weight DESC
LIMIT $limit
"""

def run_query(limit_edges, uri, user, password, database):
    """
    Execute the edge query and return a list of dictionaries,
    one per edge, containing source/target node names, edge final weight, edge count, and node counts.
    """
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as s:
            edges = [dict(r) for r in s.run(Q_EDGES, limit=limit_edges)] 
    finally:
        driver.close()
    return edges

def normalize(vals, out_min, out_max):
    """
    This function implements Linear Interpolation. 
    Iam using this function to adjust the size of nodes and the width of edges.
    """

    # General formula : y = y1 ​+ (x − x1​) * ( (y2 - y1) / (x2 - x1) )
    
    # My implementation computes : 
    # normalized(v) = out_min + (v − vmin​) * ( (​out_max − out_min) / (v_max − v_min) )​
    # vmin and vmax are the minimum and maximum of the original values
    # (out_min, out_max) are the new range
    # For every value in vals list (your “x”), you find the corresponding normalized value (your “y”).

    # With this function , we manage to preserve exactly the same linear relationship 
    # between the original values (node count or edge weight) 
    # and the displayed values (node size or edge thickness).

    # The normalize() function does not change the relationship between values, 
    # Instead, it simply converts those values to a different scale.

    # So the final visualization is valid.

    vals = list(vals)
    if not vals: return []
    vmin, vmax = min(vals), max(vals)

    # when all input values are the same
    if math.isclose(vmin, vmax): 
        mid = (out_min + out_max) / 2.0 # then, computes the midpoint of the output range
        return [mid]*len(vals) # returns a list where every item is mid, with the same length as vals
    
    scale = (out_max - out_min) / (vmax - vmin)
    return [out_min + (v - vmin) * scale for v in vals]

# The following function builds a better visualization of Knowledge Graph. 
def build_vis(edges, title="Knowledge Graph Snapshot"):
    # Create the PyVis canvas (HTML graph)
    net = Network(height="1000px", width="100%", notebook=False, bgcolor="#ffffff", font_color="#222")

    # Initial spacing (repulsion + basic layout hint)
    net.barnes_hut(gravity=-6000, central_gravity=0.01, spring_length=120, spring_strength=0.015)

    # Visual options: node/edge style, physics, interaction
    net.set_options("""
    {
    "nodes": {
        "shape": "dot",
        "font": { "size": 100, "face": "arial", "bold": "bold", "strokeWidth": 2, "strokeColor": "#000000"}
    },
    "edges": {
        "arrows": { "to": { "enabled": false } },
        "smooth": { "type": "dynamic" }
    },
    "layout": { "improvedLayout": true, "randomSeed": 42 },
    "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
        "gravitationalConstant": -600,
        "centralGravity": 0.01,
        "springConstant": 0.06,
        "springLength": 280,
        "damping": 2,
        "avoidOverlap": 1
        },
        "minVelocity": 2,
        "stabilization": {"enabled": true, "iterations": 200, "fit": true}
    },            
    "interaction": { "hover": true, "zoomView": true, "dragView": true, "dragNodes": true}
    }
    """)

    # --- Build node sizes from node counts (only for nodes that appear in edges) ---
    count_map = {}
    for e in edges:
        s, t = e["Source"], e["Target"]
        sc = e.get("SourceCount")
        tc = e.get("TargetCount")

        count_map[s] = sc
        count_map[t] = tc

    # Convert dict to a list of (name, count) pairs.
    nodes_list = list(count_map.items())

    # Extract counts, then normalize them to desired node sizes (20..200)
    counts = []
    for pair in nodes_list:
        count = pair[1]  # take only the second element from the (name, count) pair 
        counts.append(count)

    # Normalize node sizes to the range (20, 200).
    sizes = normalize(counts, 20, 200)

    # Add nodes to the graph, matching each node with its corresponding size by index.
    for i in range(len(nodes_list)):
        name  = nodes_list[i][0]
        count = nodes_list[i][1]
        size  = sizes[i]

        net.add_node(
            name,
            label=name,
            size=size,             
            title=f"Concept: {name}, Count: {count}",
            color="#FFD700"
        )


    # Collect all edge weights.
    weights = []
    for e in edges:
        weights.append(float(e["Weight"]))

   # Normalize edge widths to the range (1.0, 30.0)
    widths = normalize(weights, 1.0, 30.0)

    # Add edges to the graph, pairing each edge with its corresponding width by index.
    for i in range(len(edges)):
        e = edges[i]
        w = widths[i]

        net.add_edge(
            e["Source"], e["Target"],
            title=(
            f"Source: {e['Source']}, "
            f"Target:  {e['Target']}, "
            f"weight:  {e['Weight']:.3f}, "
            f"count:  {e['Count']}"
            ),
            width=w,
            color="#039EFF"
        )

    # Export interactive HTML
    net.write_html("knowledge_graph.html", open_browser=True, notebook=False)

# We call this wrapper from api.
def make_better_graph_visualization(
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "22222222",
    database: str = "knowledge-graph",
    limit_edges: int = 25):
    
    # First of all , check if the graph contains any data (nodes/rels)
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as s:
            # if i have at least 1 edge. 
            rec_any_edge = s.run("MATCH ()-[r]->() RETURN 1 AS ok LIMIT 1").single()
            if rec_any_edge is None: 
                return  # if graph empty , then skip visualization
            
    finally:
        driver.close()

    edges = run_query(limit_edges, uri, user, password, database)
    if not edges:
        return  # empty graph: skip build_vis entirely
    
    build_vis(edges)

