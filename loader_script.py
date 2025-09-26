from neo4j import GraphDatabase
import json
from collections import defaultdict, Counter
import hashlib
from pathlib import Path

def run_neo4j_loader(intermediate_json_path: str, 
                     uri: str = "bolt://localhost:7687", 
                     user: str = "neo4j", 
                     password: str="11111111",
                     database: str = "neo4j", 
                     repo_url: str = "unknown-repo-url") -> tuple[int, int]:

    """
    Load the intermediate KG JSON (nodes/edges) into Neo4j.

    Returns (nodes_count, rels_count) and prints API-friendly signals:
    NEO4J_NODES=<int>, NEO4J_RELS=<int>, NEO4J_OK=1
    """

    # Validate input path
    in_p = Path(intermediate_json_path).resolve()
    if not in_p.exists():
        raise FileNotFoundError(f"Intermediate not found: {in_p}")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as s:
            # Ping DB
            # health check / connectivity test
            # Confirms that the Python driver can connect to the Neo4j database
            # If Ping: 1, everything is ok
            print("Ping:", s.run("RETURN 1 AS ok").single()["ok"])

            # Read intermediate JSON (nodes/edges)
            with open(in_p, "r", encoding="utf-8") as f:
                data = json.load(f)
            nodes = data.get("nodes", [])
            edges = data.get("edges", [])

            # Namespacing for synthetic names (avoid cross-repo collisions)
            # Build a short namespace from the repo URL (first 12 hex chars of SHA1)
            GITHUB_URL = repo_url or "unknown-repo-url"
            NAMESPACE = hashlib.sha1(GITHUB_URL.encode("utf-8")).hexdigest()[:12]

            # Rename only synthetic names (<TYPE>_ANON_*) and the special REPO_ANON_GLOBAL_* (avoid cross-repo collisions)
            rename = {}
            for n in nodes:
                t, nm = n.get("type"), n.get("name")
                if not (isinstance(nm, str) and t):
                    continue
                # match <TYPE>_ANON_*  (+ special case for REPO_ANON_GLOBAL_)
                if nm.startswith(f"{t}_ANON_") or (t == "REPO" and nm.startswith("REPO_ANON_GLOBAL_")):
                    new_nm = f"{nm}__{NAMESPACE}"
                    rename[(t, nm)] = new_nm
                    n["name"] = new_nm

            # update edge endpoints (Update relationship endpoints to use the new renamed node names)
            for e in edges:
                kf = (e.get("from_type"), e.get("from"))
                kt = (e.get("to_type"),   e.get("to"))
                if kf in rename: e["from"] = rename[kf]
                if kt in rename: e["to"]   = rename[kt]


            # counts & normalized_appearances ΠΡΙΝ ΤΟ MERGE ===
            # Pre-compute counts & normalized_appearances BEFORE MERGE
            # "normalized_appearances" = count(tuple)/total and this is stored on nodes/edges.

            """
            Create a simple tuple that uniquely identifies a node.

            Fields included: type, name, weight, depth (i.e. all node's information)

            We use it with Counter to find how many times
            each unique node appears in the JSON.
            """
            def node_key(n):
                return (n.get("type"), n.get("name"), n.get("weight"), n.get("depth"))

            """
            Create a simple tuple that uniquely identifies a relationship.

            Fields included: type, from_type, from, from_weight, to_type, to, to_weight, edge_weight, final_weight 
            (i.e. all relationship's information)

            We use it with Counter to find how many times
            each relationship node appears in the JSON.
            """
            def edge_key(e):
                return (
                    e.get("type"),
                    e.get("from_type"), e.get("from"), e.get("from_weight"),
                    e.get("to_type"),   e.get("to"),   e.get("to_weight"),
                    e.get("edge_weight"), e.get("final_weight"),
                )

            # These counts how many times each unique node or edge appears in the JSON.
            # Counter counts how many times that same tuple appears
            node_counts = Counter(node_key(n) for n in nodes)
            edge_counts = Counter(edge_key(e) for e in edges)

            total_nodes = len(nodes) # total number of nodes in the JSON
            total_edges = len(edges) # total number of edges in the JSON
            
            # For every node type (CLASS, METHOD, FILE, etc.),
            # make sure Neo4j knows that (name, weight, depth) must be unique.
            # This keeps MERGE consistent and avoids duplicates.
            # Make the following constraint
            labels = {n["type"] for n in nodes if n.get("type")}
            labels.update({e.get("from_type") for e in edges if e.get("from_type")})
            labels.update({e.get("to_type")   for e in edges if e.get("to_type")})
            for lbl in sorted(labels):
                s.run(f"""
                    CREATE CONSTRAINT uniq_{lbl}_all IF NOT EXISTS
                    FOR (n:`{lbl}`)
                    REQUIRE (n.name, n.weight, n.depth) IS UNIQUE
                """)

            # Add nodes into Neo4j (or reuse them if they already exist)
            # Nodes are grouped by type (e.g. CLASS, FUNCTION, FILE)
            # MERGE uses (name, weight, depth) to identify each node
            # If a node with these properties already exists → reuse it
            # If it doesn’t exist → create a new node
            # Finally, store how often this node appears in the JSON (normalized_appearances) 
            by_label = defaultdict(list)
            for n in nodes:
                t, name = n.get("type"), n.get("name")
                if not (t and name is not None):
                    continue
                nk = node_key(n)
                norm = (node_counts[nk] / total_nodes) if total_nodes else 0.0
                by_label[t].append({
                    "name": name,
                    "weight": n.get("weight"),
                    "depth": n.get("depth"),
                    "normalized_appearances": norm
                })

            for lbl, rows in by_label.items():
                s.run(f"""
                    UNWIND $rows AS row
                    MERGE (n:`{lbl}` {{
                        name:   row.name,
                        weight: row.weight,
                        depth:  row.depth
                    }})
                    SET n.normalized_appearances = row.normalized_appearances
                """, rows=rows)

            # Prepare relationships before inserting into Neo4j
            # Group edges by (relationship type, from-node type, to-node type).
            # This way we can send them to the database in batches instead of one by one.
            # In this way, we improve the neo4j performance.
            groups = defaultdict(list)
            for e in edges:
                # Extract all important fields from the edge
                rt, ft, tt = e.get("type"), e.get("from_type"), e.get("to_type")
                fr, to = e.get("from"), e.get("to")
                fw, tw = e.get("from_weight"), e.get("to_weight")
                ew, fw2 = e.get("edge_weight"), e.get("final_weight")

                # If any required field is missing → skip this edge
                if not (rt and ft and tt and fr is not None and to is not None and
                        fw is not None and tw is not None and ew is not None and fw2 is not None):
                    continue

                # Build a unique key for this edge
                # and compute how many times it appears in the JSON (normalized appearances)
                ek = edge_key(e)
                norm = (edge_counts[ek] / total_edges) if total_edges else 0.0

                # Copy all edge data and add the normalized appearances
                row = dict(e)
                row["normalized_appearances"] = norm
                groups[(rt, ft, tt)].append(row)

            # Create or reuse relationships in Neo4j
            for (rel_type, from_type, to_type), rows in groups.items():
                s.run(f"""
                    UNWIND $rows AS row
                    // Find the source node and target node by its label, name, and weight
                    MATCH (a:`{from_type}` {{
                        name:   row.from,
                        weight: row.from_weight
                    }})
                    MATCH (b:`{to_type}` {{
                        name:   row.to,
                        weight: row.to_weight
                    }})
                    // MERGE the relationship with ALL the properties of the edge
                    MERGE (a)-[r:`{rel_type}` {{
                        from:         row.from,
                        to:           row.to,
                        from_type:    row.from_type,
                        to_type:      row.to_type,
                        from_weight:  row.from_weight,
                        to_weight:    row.to_weight,
                        edge_weight:  row.edge_weight,
                        final_weight: row.final_weight
                    }}]->(b)
                    SET r.normalized_appearances = row.normalized_appearances
                """, rows=rows)

            # Sanity check
            # Count how many nodes and relationships are now in the DB
            nc = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rc = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            print(f"[DONE] Neo4j load complete. nodes={nc}, relationships={rc}")
            print(f"NEO4J_NODES={nc}")
            print(f"NEO4J_RELATIONSHIPS={rc}")
            print("NEO4J_OK=1")
            return nc, rc

    finally:
        driver.close() # Always close the DB connection

