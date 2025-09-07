import json
import argparse
from pathlib import Path
from copy import deepcopy

def remove_nested_attributes(classes):
    # Work on a deep copy to avoid modifying original data
    classes = deepcopy(classes)

    # Build mapping: class name -> set(attributes)
    class_sets = {cls.get("name", ""): set(cls.get("attributes", [])) for cls in classes}

    # Build children_map: which classes are "children" of others
    children_map = {cls.get("name", ""): set() for cls in classes}
    for outer_cls in classes:
        outer_name = outer_cls.get("name", "")
        outer_attr = class_sets[outer_name]
        for inner_cls in classes:
            inner_name = inner_cls.get("name", "")
            if outer_name == inner_name:
                continue
            inner_attr = class_sets[inner_name]
            # If outer has all attributes of inner and something more, mark inner as child
            if outer_attr.issuperset(inner_attr) and outer_attr != inner_attr:
                children_map[outer_name].add(inner_name)

    # Recursively collect attributes of all children
    def collect_child_attrs(cls_name, visited=None):
        if visited is None:
            visited = set()
        if cls_name in visited:
            return set()
        visited.add(cls_name)

        all_attrs = set()
        for child in children_map[cls_name]:
            child_attrs = class_sets[child]
            all_attrs.update(child_attrs)
            # Recurse into children of child
            all_attrs.update(collect_child_attrs(child, visited))
        return all_attrs

    # Remove attributes that belong to children from parent classes
    for cls in classes:
        cls_name = cls.get("name", "")
        child_attrs = collect_child_attrs(cls_name)
        cls["attributes"] = [a for a in cls.get("attributes", []) if a not in child_attrs]

    return classes

def clean_c_output_json(input_path: str, output_path: str):
    # Load JSON input file
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Iterate through file entries and clean nested attributes in classes
    for file_obj in data:
        if isinstance(file_obj, list):
            for item in file_obj:
                if isinstance(item, dict) and "classes" in item:
                    item["classes"] = remove_nested_attributes(item["classes"])

    # Write cleaned data to new JSON file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[CLEAN][C] {input_path} -> {output_path}")
