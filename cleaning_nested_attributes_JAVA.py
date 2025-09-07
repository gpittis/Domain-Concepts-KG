import json
import argparse
from pathlib import Path
from copy import deepcopy

def remove_nested_attributes_from_list(classes_list):
    # Make a deep copy so we don’t modify the original input
    classes_list = deepcopy(classes_list)

    def collect_all_nested_attrs(cls):
        """Return all attributes from nested classes (recursively)."""
        all_attrs = set()
        for nested in cls.get("nested_classes", []):
            all_attrs.update(nested.get("attributes", [])) # add direct attributes
            all_attrs.update(collect_all_nested_attrs(nested)) # add attributes from deeper nesting
        return all_attrs

    def clean_class(cls):
        # Clean nested classes first (recursively)
        for nested in cls.get("nested_classes", []):
            clean_class(nested)

        # Remove attributes that also exist in nested classes
        nested_attrs = collect_all_nested_attrs(cls)
        cls_attrs = set(cls.get("attributes", []))
        cls["attributes"] = list(cls_attrs - nested_attrs)

    # Clean each class in the list
    for cls in classes_list:
        clean_class(cls)

    return classes_list

def clean_java_output_json(input_path: str, output_path: str):
    # Load input JSON
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # For each file, clean class attributes
    for file_obj in data:
        if isinstance(file_obj, list):
            for item in file_obj:
                if isinstance(item, dict) and "classes" in item:
                    item["classes"] = remove_nested_attributes_from_list(item["classes"])

    # Save cleaned JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[CLEAN][JAVA] {input_path} -> {output_path}")

