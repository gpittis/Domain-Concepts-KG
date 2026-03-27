import os
import json
from collections import defaultdict
from pathlib import Path


# ---------- Node weights ----------
NODE_WEIGHTS = {
    "REPO": 0.05, # Repository 
    "FILE": 0.50, # File 
    "IMPORT": 0.60, # Import 
    "GLOBAL_VAR": 0.65, # Global variable 
    "CLASS": 0.95, # Top-level class
    "NESTED_CLASS": 0.45, # Class defined inside another class/function
    "FUNCTION": 0.90, # Top-level function
    "NESTED_FUNCTION": 0.45, # Function defined inside another function
    "METHOD": 0.85, # Class method
    "PARAM": 0.40, # Function/method parameter
    "LOCAL_VAR": 0.20, # Local variable inside a function/method
    "ATTRIBUTE": 0.65, # Class attribute
}

# Decay factor for nested nodes: deeper levels lose importance
LAMBDA_DECAY = 0.95

# -----------------------------------------------------


def _has_nonempty_attr(cls_dict) -> bool:
    """
    Check if a class dictionary has any non-empty attribute name, method name.
    Used as a filter to avoid adding empty/invalid attributes to the graph.
    """
    for a in (cls_dict.get("attributes", []) or []):
        if (a or "").strip():  # only count non-empty strings
            return True
        
    # Methods
    for m in (cls_dict.get("methods", []) or []):
        if isinstance(m, dict):
            raw_name = (m.get("name") or "").strip()
            if raw_name:
                return True

    return False

def _has_signal_fn(fn_dict) -> bool:
    """
    Check if a function dictionary has any meaningful content (params or local vars).
    Used as a filter to ignore empty functions.
    """
    for p in (fn_dict.get("params", []) or []):
        if (p or "").strip():
            return True
    for lv in (fn_dict.get("local_variables", []) or []):
        if (lv or "").strip():
            return True
    return False

def transform_to_kg(cleaned_json) -> dict:
    """
    Transform a cleaned static analysis JSON into a Knowledge Graph schema.
    Produces:
      - nodes: list of entities (files, classes, functions, variables, etc.)
      - edges: list of relationships between those entities
    Each node/edge has a type, weight, and depth information.
    """
    # --- Synthetic names for entities without explicit names (only for FILE/CLASS/FUNCTION/METHOD & nested) ---
    _counters = defaultdict(int)

    def synth_name(kind: str, parent_hint: str | None) -> str:
        
        """
        Generate a stable synthetic name for core graph nodes when no name exists.
        kind: one of {"FILE", "CLASS", "NESTED_CLASS", "FUNCTION", "NESTED_FUNCTION", "METHOD"}
        
        Example:
        synth_name("CLASS", "myfile.cpp") → "CLASS_ANON_myfile.cpp_1"
        """
        key = (kind, parent_hint or "GLOBAL")
        _counters[key] += 1
        base = (parent_hint or "GLOBAL").replace(os.sep, "_")
        return f"{kind}_ANON_{base}_{_counters[key]}"

    nodes = []
    edges = []
    node_weights = {}  # mapping name → final_weight

    def add_node(node_type, name, depth=0):
        """
        Add a node to the graph with type, name, depth, and weight based on node's type.
        - The base weight comes from NODE_WEIGHTS.
        - For nested nodes, apply exponential decay based on depth.
        - Save both the node and its weight into the nodes list and node_weights dict.
        """
        base = NODE_WEIGHTS.get(node_type, 0.0)
        # Apply decay only for nested function/class nodes
        # nested → αποδυνάμωση με βάση το depth (depth=1 = πρώτο επίπεδο nesting)
        if node_type in ("NESTED_FUNCTION", "NESTED_CLASS"):
            levels_beyond_first = max(depth - 1, 0) # start decay after first nesting
            decay = (LAMBDA_DECAY ** levels_beyond_first)
        else:
            decay = 1.0
        final_weight = round(base * decay, 6) # Compute final weight and round to 6 decimals

        # Store weight for later edge calculations
        node_weights[(node_type, name)] = final_weight

        # Build node object and add to nodes list
        node_obj = {
            "type": node_type,
            "name": name,
            "weight": final_weight,
            "depth": depth
        }
        nodes.append(node_obj)

    def add_edge(edge_type, source, target, from_type=None, to_type=None):
        """
        Add an edge (relationship) between two nodes.
        - from_w, to_w: the weights of from and target nodes
        - final_w: average of (from_w, to_w) → ensures balanced influence
        - Every weight (from node weight, target node weight) are considered equally important.
        """
        from_w = node_weights.get((from_type, source), 0.0)
        to_w   = node_weights.get((to_type, target), 0.0)

        # Compute the final edge weight as the average of the two components
        final_w = round((from_w + to_w) / 2, 6)

        # Build edge object and add to edges list
        edges.append({
            "type": edge_type, # type of relationship
            "from": source, # name of from node
            "to": target, # name of target node
            "from_type": from_type, # type of from node
            "to_type": to_type, # type of target node 
            "from_weight": from_w, # weight of from node
            "to_weight": to_w, # weight of target node
            "final_weight": final_w # final weight = (from_w + to_w)/2
        })

    def iter_files(payload):
        
        """
        Normalize parser output into a single file_entry dict
        with keys: name, imports, global_variables, classes, functions.

        Input format (always):
        [
            {"file": ...},
            {"imports": [...]},
            {"global_variables": [...]},
            {"functions": [...]},
            {"classes": [...]}
        ]
        """

        # Case : [ ...file_blocks... ] where each block is a list of {key: value} dicts
        if isinstance(payload, list):
            for block in payload:
                merged = {"name": None, "imports": [], "global_variables": [], "classes": [], "functions": []}
                if isinstance(block, list):
                    # Merge multiple dicts from the same block
                    for item in block:
                        if not isinstance(item, dict):
                            continue
                        if "file" in item:
                            merged["name"] = item["file"]
                        elif "imports" in item:
                            merged["imports"] = item.get("imports", []) or []
                        elif "global_variables" in item:
                            merged["global_variables"] = item.get("global_variables", []) or []
                        elif "classes" in item:
                            merged["classes"] = item.get("classes", []) or []
                        elif "functions" in item:
                            merged["functions"] = item.get("functions", []) or []
                else:
                    # Fallback if block is already a dict
                    merged.update({
                        "name": block.get("name") or block.get("file"),
                        "imports": block.get("imports", []) or [],
                        "global_variables": block.get("global_variables", []) or [],
                        "classes": block.get("classes", []) or [],
                        "functions": block.get("functions", []) or [],
                    })
                if not merged["name"]:
                    merged["name"] = synth_name("FILE", None) # synthetic name if missing
                yield merged
            return
        # Any other format: yield nothing
        return

    # --- Recursive walker for functions/methods (infinite depth supported) ---
    def walk_function(fn_dict, parent_name, parent_is_file=False, is_method=False, parent_label=None, nesting_depth=0):
        raw_name = fn_dict.get("name") # get the function name

        # If function name is empty, keep only if it has a signal (params or local vars non-empty)
        if not (raw_name or "").strip():
            if not _has_signal_fn(fn_dict):
                return  # skip this function/method entirely

        # Node label depends on context
        if is_method:
            node_label = "METHOD" # if is_method = True , then the function belongs to a class , so it is a METHOD
        else:
            node_label = "FUNCTION" if parent_is_file else "NESTED_FUNCTION" # if belongs to a file, then it is FUNCTION
            # else if its parent node is a function , then we have a NESTED_FUNCTION

        # Use existing name or synthetic if empty (at this point we know it has some signal)
        fn_name = (raw_name or "").strip() or synth_name(node_label, parent_name)

        # Add node with decay if nested
        if node_label == "NESTED_FUNCTION":
            add_node(node_label, fn_name, depth=nesting_depth)
            current_nested_depth = nesting_depth   # αυτός ο κόμβος είναι nested
        else:
            add_node(node_label, fn_name)
            current_nested_depth = 0               # δεν είναι nested κόμβος

        # Add edge from parent (connect the function with its parent)
        if parent_is_file:
            add_edge("FILE_CONTAINS", parent_name, fn_name,
             from_type="FILE", to_type=node_label)             # File → Function
        else:
            if is_method:
                add_edge("HAS_METHOD", parent_name, fn_name,
                 from_type=parent_label, to_type="METHOD")             # Class → Method
            else:
                add_edge("HAS_NESTED_FUNCTION", parent_name, fn_name,
                 from_type=parent_label, to_type="NESTED_FUNCTION")    # Function/Method → Nested Function

        # Parameters of the function — αγνόησε κενά/None/λευκά
        for p in (fn_dict.get("params", []) or []):
            pname = (p or "").strip()
            if not pname:
                continue
            add_node("PARAM", pname)
            add_edge("HAS_PARAM", fn_name, pname, from_type=node_label, to_type="PARAM")

        # Local variables of the function — ignore empty/whitespace
        for lv in (fn_dict.get("local_variables", []) or []):
            lvname = (lv or "").strip()
            if not lvname:
                continue
            add_node("LOCAL_VAR", lvname)
            add_edge("HAS_LOCAL_VAR", fn_name, lvname, from_type=node_label, to_type="LOCAL_VAR")

        # Nested functions inside function
        next_depth_for_nested_fn = (current_nested_depth + 1) if current_nested_depth > 0 else 1
        for nf in fn_dict.get("nested_functions", []) or []:
            if isinstance(nf, dict):
                walk_function(nf, parent_name=fn_name, parent_is_file=False, is_method=False,
                      parent_label=node_label, nesting_depth=next_depth_for_nested_fn)

        # Nested classes inside function
        next_depth_for_nested_cls = (current_nested_depth + 1) if current_nested_depth > 0 else 1
        for nc in fn_dict.get("nested_classes", []) or []:
            if isinstance(nc, dict):
                walk_class(nc, file_name=None, parent_name=fn_name, parent_label=node_label, nesting_depth=next_depth_for_nested_cls)

    # --- Recursive walker for classes (infinite depth supported) ---
    def walk_class(cls_dict, file_name, parent_name=None, parent_label=None, nesting_depth=0):
        # A class can be either top-level (inside a file) or nested (inside another class or function).
        # If it has a parent_name → it is a nested class.
        is_nested = parent_name is not None

        # CLASS node if belongs to a file
        # NESTED_CLASS node if belongs to another class
        node_label = "NESTED_CLASS" if is_nested else "CLASS" 

        raw_name = cls_dict.get("name") # get the class name

        # Αν το name είναι κενό, κρατάμε τη κλάση μόνο αν έχει τουλάχιστον 1 attribute μη κενό ή 1 μεθοδο μη κενή
        if not (raw_name or "").strip():
            if not _has_nonempty_attr(cls_dict):
                return  # skip εντελώς αυτή την class

        # Όνομα: υπάρχον ή συνθετικό (εδώ είμαστε σίγουροι ότι έχει "σήμα" attribute)
        cls_name = (raw_name or "").strip() or synth_name(node_label, parent_name or file_name)

        # Add node for this class
        # If nested → decay factor affects weight
        if node_label == "NESTED_CLASS":
            add_node(node_label, cls_name, depth=nesting_depth)
            current_nested_depth = nesting_depth
        else:
            add_node(node_label, cls_name)
            current_nested_depth = 0

        # Edge προς γονέα (Connect this class to its parent)
        if parent_name:
            # Ανεξάρτητα αν ο γονέας είναι Class/Function
            add_edge("HAS_NESTED_CLASS", parent_name, cls_name,
             from_type=parent_label, to_type=node_label)
        else:
            add_edge("FILE_CONTAINS", file_name, cls_name,
             from_type="FILE", to_type=node_label) # ανήκει σε file (άρα είναι top-level)

        # Attributes of the Class — αγνόησε κενά/None/λευκά
        for attr in (cls_dict.get("attributes", []) or []):
            aname = (attr or "").strip()
            if not aname:
                continue
            add_node("ATTRIBUTE", aname)
            add_edge("HAS_ATTRIBUTE", cls_name, aname,
         from_type=node_label,
         to_type="ATTRIBUTE")

        # Methods of the Class
        # Methods: ΔΕΝ είναι nested nodes → δώσε nesting_depth=0
        # ώστε οι nested functions μέσα τους να ξεκινήσουν από depth=1
        for m in cls_dict.get("methods", []) or []:
            if isinstance(m, dict):
                walk_function(m, parent_name=cls_name, parent_is_file=False, is_method=True,
              parent_label=node_label, nesting_depth=0)

        # Nested classes (recursive handling , increment depth)
        next_depth_for_nested_cls = (current_nested_depth + 1) if current_nested_depth > 0 else 1
        for nc in cls_dict.get("nested_classes", []) or []:
            if isinstance(nc, dict):
                walk_class(nc, file_name=file_name, parent_name=cls_name, parent_label=node_label, nesting_depth=next_depth_for_nested_cls)

    # --- Repository root node ---
    repo_name = synth_name("REPO", None)
    add_node("REPO", repo_name)

    # ---- Κύρια λογική ----
    for file_entry in iter_files(cleaned_json):
        file_name = file_entry.get("name") or synth_name("FILE", None)
        add_node("FILE", file_name)

        # Σύνδεση FILE → REPO
        add_edge("EXISTS_IN", file_name, repo_name, from_type="FILE", to_type="REPO")

        # IMPORTS
        for imp in (file_entry.get("imports", []) or []):
            if imp:
                add_node("IMPORT", imp)
                add_edge("IMPORTS", file_name, imp, from_type="FILE", to_type="IMPORT")

        # GLOBAL VARS
        for gv in (file_entry.get("global_variables", []) or []):
            if gv:
                add_node("GLOBAL_VAR", gv)
                add_edge("HAS_GLOBAL_VAR", file_name, gv, from_type="FILE", to_type="GLOBAL_VAR")

        # CLASSES (top-level)
        for cls in file_entry.get("classes", []) or []:
            if isinstance(cls, dict):
                walk_class(cls, file_name=file_name, parent_name=None, parent_label=None, nesting_depth=0)

        # FUNCTIONS (top-level)
        for fn in file_entry.get("functions", []) or []:
            if isinstance(fn, dict):
                walk_function(fn, parent_name=file_name, parent_is_file=True, is_method=False, parent_label="FILE", nesting_depth=0)

    return {"nodes": nodes, "edges": edges}


def run_sg_builder(cleaned_json_path: str, output_path: str | None = None) -> Path:
    """
    Παίρνει το cleaned JSON (αφού έχει περάσει από το concept filter),
    καλεί transform_to_kg(...) και γράφει ένα ενδιάμεσο JSON με nodes/edges.

    - cleaned_json_path: πλήρες path του *_cleaned_from_non_concepts.json
    - output_path: (προαιρετικό) τελικό path. Αν δεν δοθεί, γράφει δίπλα στο input:
        <input_stem>_kg.json
    Επιστρέφει το Path του παραγόμενου KG JSON.
    """
    in_p = Path(cleaned_json_path).resolve()
    if not in_p.exists():
        raise FileNotFoundError(f"Input not found: {in_p}")

    # Προεπιλογή ονόματος εξόδου, δίπλα στο input
    if output_path is None:
        # π.χ. foo_cleaned_from_non_concepts.json -> foo_kg.json
        base_stem = in_p.stem
        base_stem = base_stem.replace("_cleaned_from_non_concepts", "")
        out_p = in_p.with_name(base_stem + "_kg.json")
    else:
        out_p = Path(output_path).resolve()

    # Ensure parent directory exists
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # Φόρτωσε το cleaned JSON
    with open(in_p, "r", encoding="utf-8") as f:
        cleaned_json = json.load(f)

    # Transform to knowledge graph structure
    kg_json = transform_to_kg(cleaned_json)

    # Γράψε το αποτέλεσμα
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(kg_json, f, indent=2, ensure_ascii=False)
    
    # print(f"[DONE] KG JSON: {out_p}")
    # print(f"KG_JSON={out_p}")

    return out_p


        
