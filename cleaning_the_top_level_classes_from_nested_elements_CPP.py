import json
import argparse
from pathlib import Path
from copy import deepcopy

def remove_nested_members(classes):
    classes = deepcopy(classes) # Work on a copy, keep original intact

    # Build mapping: class name -> sets of attributes and methods
    class_sets = {}
    for cls in classes:
        attr_set = set(cls.get("attributes", []))
        method_set = set(m["name"] for m in cls.get("methods", []))
        class_sets[cls["name"]] = {"attributes": attr_set, "methods": method_set}

    # Find child classes (subset of another class)
    children_map = {cls["name"]: set() for cls in classes}
    for outer_cls in classes:
        for inner_cls in classes:
            if outer_cls["name"] == inner_cls["name"]:
                continue
            outer_attr = class_sets[outer_cls["name"]]["attributes"]
            outer_method = class_sets[outer_cls["name"]]["methods"]
            inner_attr = class_sets[inner_cls["name"]]["attributes"]
            inner_method = class_sets[inner_cls["name"]]["methods"]

            # If outer contains all members of inner and something more, then inner is a child
            if (outer_attr.issuperset(inner_attr) and outer_method.issuperset(inner_method)
                and (outer_attr != inner_attr or outer_method != inner_method)):
                children_map[outer_cls["name"]].add(inner_cls["name"])

    # Recursively collect all child members (attributes and methods)
    def collect_child_members(cls_name, visited=None):
        if visited is None:
            visited = set()
        if cls_name in visited:
            return set(), set()
        visited.add(cls_name)

        all_attrs = set()
        all_methods = set()
        for child in children_map[cls_name]:
            child_attrs = class_sets[child]["attributes"]
            child_methods = class_sets[child]["methods"]
            all_attrs.update(child_attrs)
            all_methods.update(child_methods)
            # Recursively include children of child
            sub_attrs, sub_methods = collect_child_members(child, visited)
            all_attrs.update(sub_attrs)
            all_methods.update(sub_methods)
        return all_attrs, all_methods

    # Remove inherited (child) members from each outer class
    for cls in classes:
        child_attrs, child_methods = collect_child_members(cls["name"])
        cls["attributes"] = [a for a in cls.get("attributes", []) if a not in child_attrs]
        cls["methods"] = [m for m in cls.get("methods", []) if m["name"] not in child_methods]

    return classes


def clean_cpp_output_json(input_path: str, output_path: str):
    # Load JSON
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Clean classes in each file object
    for file_obj in data:
        if isinstance(file_obj, list):
            for item in file_obj:
                if isinstance(item, dict) and "classes" in item:
                    item["classes"] = remove_nested_members(item["classes"])

    # Save cleaned JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[CLEAN][CPP] {input_path} -> {output_path}")

