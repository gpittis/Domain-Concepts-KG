import libcst as cst
from typing import List, Dict, Optional
import os
import json
from pathlib import Path
import tempfile

class CodeAnalyzer(cst.CSTVisitor):

    # A Visitor in LibCST is a class that walks the nodes of a python file’s Concrete Syntax Tree (CST) without modifying it (read-only).
    # It is used to analyze/collect information about the code.
    # In LibCST, a visitor is a subclass of the CSTVisitor class.
    # Each time the visitor enters a node, a visit method is called.
    # Each time the visitor leaves a node, a leave method is called.

    def __init__(self):

        # Names of imported libraries or modules.
        # Filled when visiting Import or ImportFrom nodes.
        self.imports: List[str] = [] 

        # List of functions encountered in the code.
        # Each function is stored as a dictionary with metadata 
        # (e.g. name, params, local_variables, nested structures)
        self.functions: List[Dict] = []

        # List of classes encountered in the code.
        # Each class is stored as a dictionary with metadata 
        # (e.g. name, attributes, methods, nested structures)
        self.classes: List[Dict] = []

        # Variables defined at the top-level (i.e. global_variables)
        self.global_vars: List[str] = []

        # All comments found in the source code, 
        # including inline comments (#) and multiline docstrings ("""...""")
        self.comments: List[str] = []

        # Tracks the class currently being visited.
        self.current_class: Optional[Dict] = None

        # Tracks the function currently being visited.
        self.current_function: Optional[Dict] = None

        # Stack of active functions (top and nested functions). A dict is pushed on enter and popped on leave.
        # The top (function_stack[-1]) is always the current function.
        # Nesting is detected when the stack depth > 1 
        self.function_stack: List[Dict] = []

        # Scope stack representing the scope hierarchy (module, class, function, ...)
        self.scope_stack: List[Dict] = [
            {"type": "module", "functions": self.functions, "classes": self.classes, "global_vars": self.global_vars}
        ]

    # Collects single-line comments (e.g., "# something")
    def visit_Comment(self, node: cst.Comment) -> None:
        comment_text = node.value.lstrip("#").strip()
        if comment_text:
            self.comments.append(comment_text)

    # Collects multiline comments (docstrings)
    def visit_SimpleString(self, node: cst.SimpleString) -> None:
        
        value = node.value
        # Check if it starts with triple quotes (valid docstring delimiters)
        triple_quotes = ('"""', "'''", 'r"""', "r'''", 'R"""', "R'''")
        if value.startswith(triple_quotes):
            # Remove string prefixes and surrounding quotes
            cleaned = value.strip('rRuU').strip('"').strip("'")
            cleaned = cleaned.strip()
            if cleaned:
                self.comments.append(cleaned)

    # This method visits all CST nodes corresponding to import statements.
    def visit_Import(self, node: cst.Import) -> None:
        for name in node.names:
            # The evaluated_name contains the name of the library being imported.
            # The library name is stored in the imports list.
            self.imports.append(name.evaluated_name)

    # This method visits CST nodes corresponding to "from ... import ..." statements.
    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        module = ""
        if isinstance(node.module, cst.Name):
            # node.module: The module specified after "from".
            # node.module.value contains the module name if it is a simple identifier (e.g., "skimage").
            module = node.module.value

        # If the module name is a chain of attributes (e.g., "scipy.ndimage"),
        elif isinstance(node.module, cst.Attribute):
            # then we use _flatten_module_name() to extract the full module name.
            module = self._flatten_module_name(node.module)
        
        # Check: if it is a ImportStar, ignore it
        if isinstance(node.names, cst.ImportStar):
            return

        for name in node.names:
            # The "name" structure holds the library/function being imported with "from ... import ...".
            if isinstance(name, cst.ImportAlias):
                if module:
                    # name.name.value is the actual name of the imported library/function.
                    self.imports.append(f"{module}.{name.name.value}")
                else:
                    # The "else" branch covers the case of "from import ...",
                    # which practically means the source code contains a syntax error.
                    self.imports.append(name.name.value)

    def _flatten_module_name(self, attr_node: cst.Attribute) -> str:
        # Create a list to store the individual parts of the module.
        # For example: from scipy.ndimage.filters → parts == ['scipy', 'ndimage', 'filters'].
        # attr_node.attr.value is the name of an attribute of the module.
        # As long as the current node is of type Attribute, 
        # it means there is a chain like module.attribute.attribute etc. (an attribute is essentially a submodule).
        parts = []
        while isinstance(attr_node, cst.Attribute):
            # Each time, we take the last attribute and insert it at the beginning of the list
            parts.insert(0, attr_node.attr.value)
            # attr_node may itself be another attribute, so the while loop continues.
            # If there are no more attributes, then attr_node is the module name.
            attr_node = attr_node.value
        if isinstance(attr_node, cst.Name):
            # Store the module name at the beginning of the list.
            # Join the elements of the parts list with dots and return the full module name.
            parts.insert(0, attr_node.value)
        return ".".join(parts)

    # This method is called whenever a class is found in the code.
    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        # It retrieves the class name.
        class_name = node.name.value
        # Creates a dictionary with the class’s basic information.
        class_info = {
            "name": class_name,
            "attributes": [],
            "methods": []
        }

        # Add class to the appropriate scope
        current_scope = self.scope_stack[-1]
        if current_scope["type"] == "class":
            # Nested class inside another class
            parent_class = current_scope["class_info"]
            parent_class.setdefault("nested_classes", []).append(class_info)
        elif current_scope["type"] == "function":
            # Nested class inside a function (rare but possible)
            parent_func = current_scope["func_info"]
            parent_func.setdefault("nested_classes", []).append(class_info)
        else:
            # Module level class
            self.classes.append(class_info)

        # .append(class_info) : Append class_info dict with metadata for top-level or nested classes

        # Sets self.current_class to the current class, so we know we are inside a class.
        # Update current class and push new class scope
        self.current_class = class_info
        self.scope_stack.append({"type": "class", "class_info": class_info})

        # Extract attributes from class-level assignments
        for statement in node.body.body:
            # Annotated assignment (e.g., x: int = 0)
            if isinstance(statement, cst.AnnAssign) and isinstance(statement.target, cst.Name):
                attr_name = statement.target.value
                if attr_name not in class_info["attributes"]:
                    class_info["attributes"].append(attr_name)
                    
            # Regular assignment (e.g., x = 0)
            elif isinstance(statement, cst.Assign):
                for target in statement.targets:
                    if isinstance(target.target, cst.Name):
                        attr_name = target.target.value
                        if attr_name not in class_info["attributes"]:
                            class_info["attributes"].append(attr_name)

    # This method is called after finishing the visit of the class body.
    def leave_ClassDef(self, node: cst.ClassDef) -> None:
        # Set to None because we have exited the class.
        self.current_class = None
        # Pop class scope (exit current class)
        self.scope_stack.pop()

    # This method is executed whenever a function is found in the code.
    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        # It extracts the function name.
        func_name = node.name.value
        # It retrieves the function arguments(parameters).
        args = [param.name.value for param in node.params.params]

        # It creates a dictionary containing the function name, parameters, local variables and nested functions
        func_info = {
            "name": func_name,
            "params": args,
            "local_variables": [],
            "nested_functions": []
        }

        # Look at the most recent scope
        if self.scope_stack:
            current_scope = self.scope_stack[-1]
            # if I am inside a class
            if current_scope["type"] == "class":
                # Then i have a Class method.
                class_info = current_scope["class_info"]
                class_info["methods"].append(func_info)
            # if I am inside a function
            elif current_scope["type"] == "function":
                # Then i have a Nested function.
                parent_func = current_scope["func_info"]
                parent_func.setdefault("nested_functions", []).append(func_info)
            else:
                # Module level function
                self.functions.append(func_info)
        else:
            # If no scope exists, assume module
            self.functions.append(func_info)

        # Add to scope stack - push function scope
        self.scope_stack.append({"type": "function", "func_info": func_info})

        # Push current function onto the stack and mark it as the active function.
        self.function_stack.append(func_info)
        self.current_function = func_info

    # This method is called after finishing the visit of a function body.
    def leave_FunctionDef(self, node: cst.FunctionDef) -> None:
        # Remove the current function from the stack
        self.function_stack.pop()
        # Update current_function: set to parent if stack not empty, else None
        self.current_function = self.function_stack[-1] if self.function_stack else None
        # Pop the function scope and return to the parent scope
        self.scope_stack.pop()

    # This method is called whenever an assignment statement is found.
    def visit_Assign(self, node: cst.Assign) -> None:
        # targets is a list of variable names on the left-hand side of the Assign.
        targets = [t.target.value for t in node.targets if isinstance(t.target, cst.Name)]

        # Get the type of the current scope (module, class, or function)
        current_scope = self.scope_stack[-1]["type"]

        # Collect variable names on the left-hand side of the assignment
        targets = set()
        for t in node.targets:
            if isinstance(t.target, cst.Name):
                # Simple variable (e.g., x = ...)
                targets.add(t.target.value)
            elif (
                isinstance(t.target, cst.Attribute)
                and isinstance(t.target.value, cst.Name)
                and t.target.value.value == "self"
            ):
                # Case: self.attribute = ...  , ( e.g.  self.value = 10)
                attr_name = t.target.attr.value
                # Inside a class method → record as a class attribute
                if current_scope == "function" and len(self.scope_stack) >= 2 and self.scope_stack[-2]["type"] == "class":
                    current_class = self.scope_stack[-2]["class_info"]
                    # attributes is a list
                    # check before appending to avoid duplicates
                    if attr_name not in current_class["attributes"]:
                        current_class["attributes"].append(attr_name)
                else:
                    # Not inside a class method 
                    # treat self.<attr> like a normal target
                    # (practically impossible)
                    targets.add(attr_name)

            # Assignment to a subscripted element 
            # (e.g., arr[i] = ..., dict["key"] = ... , matrix[0][1] = ...)
            elif isinstance(t.target, cst.Subscript):
                parts = [] # the parts of the Subscript
                node = t.target
                # Unroll nested Subscript nodes (e.g., config["a"]["b"], arr[0][1])
                while isinstance(node, cst.Subscript):
                    slice_node = node.slice[0].slice
                    if isinstance(slice_node, cst.Index):
                        val = slice_node.value
                        # Case: the index is a simple variable or string literal
                        # e.g., arr[i] or dict["key"]
                        # Save the index in the parts list
                        if isinstance(val, (cst.Name, cst.SimpleString)):
                            parts.append(f"[{val.value}]")
                        else:
                            # Case: the index is more complex (e.g., arr[x+1], arr[f()])
                            # Skip these cases since we only want simple subscripts
                            pass
                    else:
                        # Case: slice without explicit index (e.g., arr[:])
                        # Represent it as empty brackets
                        parts.append("[]")
                    # Move to the "value" part of the Subscript
                    node = node.value
                
                # When we reach the base object of the subscript chain
                if isinstance(node, cst.Name):
                    # Combine the base name with all collected parts.
                    # Reverse parts because they were collected inside-out.
                    # Example:
                    #   node.value = "config"
                    #   parts = ['["b"]', '["a"]']
                    #   reversed(parts) = ['["a"]', '["b"]']
                    #   full_name = 'config["a"]["b"]'
                    full_name = node.value + "".join(reversed(parts))
                    # Add the reconstructed subscript target to the set of collected targets
                    targets.add(full_name)
            
            # Case: target is a Tuple → unpack variables (e.g., x, y, z = ...)
            elif isinstance(t.target, cst.Tuple):
                for elem in t.target.elements:
                    # Simple variable
                    if isinstance(elem.value, cst.Name):
                        targets.add(elem.value.value)
                    elif (
                        isinstance(elem.value, cst.Attribute)
                        and isinstance(elem.value.value, cst.Name)
                        and elem.value.value.value == "self"
                    ):
                        # Attribute of self (class attribute)
                        attr_name = elem.value.attr.value
                        # We are inside a function, and the parent scope is a class,
                        # this means we are in a class method.
                        if current_scope == "function" and len(self.scope_stack) >= 2 and self.scope_stack[-2]["type"] == "class":
                            current_class = self.scope_stack[-2]["class_info"]
                            # If the attribute name is not already recorded, add it.
                            # I want to avoid duplicates attributes.
                            if attr_name not in current_class["attributes"]:
                                current_class["attributes"].append(attr_name)
                        else:
                            # Otherwise (not in a class method), just treat it as a normal variable target.
                            # (practically impossible)
                            targets.add(attr_name)
        
        # for targets that are local variables inside functions
        if current_scope == "function":
            current_func = self.scope_stack[-1]["func_info"]
            for t in targets:
                current_func["local_variables"].append(t)
        
        # for targets that are attributes in classes
        elif current_scope == "class":
            current_class = self.scope_stack[-1]["class_info"]
            for t in targets:
                current_class["attributes"].append(t)
        else:
            # for targets that are global variables
            for t in targets:
                self.global_vars.append(t)

    # This method is called whenever an annotated assignment statement is found.
    def visit_AnnAssign(self, node: cst.AnnAssign) -> None:

        # Get the type of the current scope
        current_scope = self.scope_stack[-1]["type"]

        # ---- Case A: simple variable name ----
        if isinstance(node.target, cst.Name):
            name = node.target.value

            # annotated local variable inside a function/method
            if current_scope == "function":
                current_func = self.scope_stack[-1]["func_info"]
                current_func["local_variables"].append(name)

            # annotated Class attribute
            elif current_scope == "class":
                current_class = self.scope_stack[-1]["class_info"]
                current_class["attributes"].append(name)
            else:
                # module/global level (i.e. annotated global variable)
                self.global_vars.append(name)

        # ---- Case B: self.attribute on the left (only meaningful in methods) ----
        elif (
        isinstance(node.target, cst.Attribute)
        and isinstance(node.target.value, cst.Name)
        and node.target.value.value == "self"
    ):
            attr_name = node.target.attr.value

            # We are in a function and its parent scope is a class,
            # so we are in a class method.
            if current_scope == "function" and len(self.scope_stack) >= 2 and self.scope_stack[-2]["type"] == "class":
                current_class = self.scope_stack[-2]["class_info"]
                # If the attribute name is not already recorded, add it.
                # I want to avoid duplicates attributes.
                if attr_name not in current_class["attributes"]:
                    current_class["attributes"].append(attr_name)

# The analyze_file() :
# 1 - takes the path of a .py file
# 2 - reads the code
# 3 - builds the Concrete Syntax Tree (CST) of the code
# 4 - visits all CST elements with a Visitor (the CodeAnalyzer() we built above)
def analyze_file(filepath: str) -> List[Dict]:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        tree = cst.parse_module(source)
        analyzer = CodeAnalyzer()
        tree.visit(analyzer)

        # The analyze_file() extracts: filename, imports, global variables, functions, classes.
        # Returns the data collected by the analyzer in a list of dictionaries.
        return [
            {"file": os.path.basename(filepath)},
            {"imports": analyzer.imports},
            {"global_variables": analyzer.global_vars},
            {"functions": analyzer.functions},
            {"classes": analyzer.classes}
        ]
    except Exception as e:
        # If an error occurs, it returns a list of dictionaries with an error message
        # return [{"file": os.path.basename(filepath)}, {"error": str(e)}]
        return None

# This function makes the static analysis of the whole codebase.
def analyze_codebase(root_path: str, json_output_file: str) -> None:
    all_results = []
    comments_data = []
    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            if filename.endswith(".py"):
                full_path = os.path.join(dirpath, filename)
                # Analysis of the codebase's python file using the analyze_file() function
                result = analyze_file(full_path)
                if result is None:
                    # Αγνόησε το αρχείο με συντακτικό λάθος
                    continue 
                all_results.append(result)

                # Parse Python file into a CST tree
                tree = cst.parse_module(open(full_path, "r", encoding="utf-8").read())

                # Analyze the CST with CodeAnalyzer
                analyzer = CodeAnalyzer()
                tree.visit(analyzer)

                # Collect comments for this file
                comments_data.append({
                    "file": os.path.basename(full_path),
                    "comments": analyzer.comments
                })

    # Save full analysis results to JSON
    with open(json_output_file, "w", encoding="utf-8") as jf:
        json.dump(all_results, jf, ensure_ascii=False, indent=2)

    # Save comments to a separate JSON
    with open("comments_python_script.json", "w", encoding="utf-8") as cf:
        json.dump(comments_data, cf, ensure_ascii=False, indent=2)


# Wrapper function around analyze_codebase:
# prepares input/output paths, runs the analyzer, and saves JSON results
def run_python_parser(codebase_dir: str, output_dir: str | None = None) -> tuple[Path, Path]:
    """
    Reads all .py files of the python codebase,
    calls analyze_codebase(...) and writes the results to fixed filenames:
      - static_analysis_output_python_lang.json
      - comments_only_python_lang.json
    Returns (main_json, comments_json).
    """
    codebase_root = Path(codebase_dir).resolve()

    # default out dir : %TEMP%/kg_api_python/python/<repo_name>
    if output_dir is None:
        base_tmp = Path(os.getenv("KG_TMP_BASE", r"C:\kg_tmp"))
        output_dir = base_tmp / "kg_api_python" / "python" / codebase_root.name
    out_root = Path(output_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    main_json = out_root / "static_analysis_output_python_lang.json"
    comments_json = out_root / "comments_only_python_lang.json"

    # analyze_codebase writes:
    #  - the main JSON at the path we pass (json_output_file)
    #  - the comments to comments_python_script.json
    old_cwd = os.getcwd()
    try:
        os.chdir(out_root)
        analyze_codebase(str(codebase_root), json_output_file=str(main_json))
        default_comments = out_root / "comments_python_script.json"
        if default_comments.exists():
            default_comments.replace(comments_json)
        else:
            # if for some reason it wasn’t created, write an empty list
            with open(comments_json, "w", encoding="utf-8") as cf:
                cf.write("[]")
    finally:
        os.chdir(old_cwd)

    # print(f"[DONE] JSON: {main_json}")
    # print(f"[DONE] Comments: {comments_json}")
    return main_json, comments_json

