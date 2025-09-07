import os
import subprocess
import sys
from lxml import etree  # The etree from lxml is used to parse the XML file.
from collections import defaultdict
import json
import tempfile
from pathlib import Path

ns = {
    # all tags without a prefix (e.g., <unit>, <function>, <decl>) belong to this namespace
    'src': 'http://www.srcML.org/srcML/src'
}

def get_full_context_path(elem):

    # List that will store the "context path"
    context = []
    # Start from the current element and go upwards in the XML tree
    while elem is not None:
        # Get the tag name without the namespace (e.g., "function", "class")
        tag = etree.QName(elem).localname

        # If the element is a class 
        if tag == 'class':
            # Extract the text inside <src:name> (this is the class name)
            name = ''.join(elem.xpath('./src:name//text()', namespaces=ns)).strip()
            # Add "class:Name" to the context list
            context.append(f'class:{name}')

        # If the element is a function
        elif tag == 'function':
            # Extract the function name from <src:name>
            name = ''.join(elem.xpath('./src:name//text()', namespaces=ns)).strip()
            # Add "function:Name"
            context.append(f'function:{name}')

        # If the element is a constructor
        elif tag == 'constructor':
            # Extract the constructor name
            name = ''.join(elem.xpath('./src:name//text()', namespaces=ns)).strip()
            context.append(f'constructor:{name}')

        # If the element is a destructor
        elif tag == 'destructor':
            # Extract the destructor name
            name = ''.join(elem.xpath('./src:name//text()', namespaces=ns)).strip()
            context.append(f'destructor:{name}')

        # Move one level up to the parent element (if any)
        elem = elem.getparent()

    # If the context list has elements:
    # - Reverse the order so it goes from outermost to innermost element
    # - Join them with " > "
    # Example: class:Foo > function:bar
    # If no context was found (e.g. we have a global function), return "<global>"
    return ' > '.join(reversed(context)) if context else '<global>'

def analyze_xml_file(file_path):

    # Loading and parsing of the XML file
    tree = etree.parse(file_path)

    # root = <unit xmlns="http://www.srcML.org/srcML/src">
    # Therefore, the <unit> tag is the root element of the tree produced by the parser.
    # The tree.getroot() is the root of the XML file.
    root = tree.getroot()

    # Data list where we will collect information about this file
    data = []

    # Save the filename (without the full path) in the data list
    data.append({"file": os.path.basename(file_path)})

    # Imports
    # In this list, i will save all the imports of a source code file.
    imports_list = []
    imports = root.xpath('.//src:import', namespaces=ns)
    for imp in imports:
        import_name = ''.join(imp.xpath('.//src:name//text()', namespaces=ns)).strip()
        imports_list.append(import_name)
    # Save the list of all imports in the data list
    data.append({"imports": imports_list})

    # === Global Variables ===
    # List that will store the names of all global variables
    globals_list = []
    
    # Find all <src:decl> elements in the XML.
    # Each <src:decl> represents a variable declaration (it can be global or local).
    decls = root.xpath('//src:decl', namespaces=ns)
    
    # Helper function to check if a declaration is in global scope
    def is_global_scope(elem):
        # Traverse in the XML tree
        while elem is not None:
            # Get the tag name (without namespace)
            tag = etree.QName(elem).localname

            # If the declaration is inside one of these (function, constructor, class, ...),
            # then it is NOT a global variable
            if tag in ('function', 'function_decl',
            'constructor', 'constructor_decl',
            'destructor', 'destructor_decl',
            'class'):
                return False
            
            # Move up one level to the parent element
            elem = elem.getparent()

        # If none of the above scopes were found, it means the variable is global
        return True
    
    # Loop through all variable declarations found
    for decl in decls:
        # Keep only the ones that are in global scope
        if is_global_scope(decl):
            # Extract the <src:name> elements (variable names)
            names = decl.xpath('./src:name', namespaces=ns)
            for name in names:
                # Get the text content of the <src:name>
                vname = ''.join(name.xpath('.//text()', namespaces=ns)).strip()

                # If we found a valid name, add it to the global variables list
                if vname:
                    globals_list.append(vname)

    # Add the list of global variables to the data list
    data.append({"global_variables": globals_list})

    # === Global Functions (Top-level functions) ===
    # List that will store information about global functions
    functions_list = []
    functions = root.xpath('.//src:function | .//src:function_decl | .//src:constructor | .//src:destructor', namespaces=ns)
    # .//src:constructor | .//src:destructor in case we have e.g. constructor of enum, interface, record
    # Iterate over each function element found
    for func in functions:
        # Get the full context path of this function (e.g., "class:Foo > function:bar")
        context = get_full_context_path(func)

        # If the context contains "class:", then this function belongs to a class.
        # So skip it, because we only want global functions here.
        if 'class:' in context:
            continue

        # Get the function name
        method_name = ''.join(func.xpath('./src:name//text()', namespaces=ns)).strip()
        # Extract the parameters of the function
        params = func.xpath('./src:parameter_list/src:parameter', namespaces=ns)
        param_list = []
        for param in params:
            # Get parameter name
            pname = ''.join(param.xpath('./src:decl/src:name//text()', namespaces=ns)).strip()
            # Add parameter name to the list
            param_list.append(f'{pname}')

        # Dictionary that stores all extracted information about one function:
        # (name, parameters, local variables)
        func_entry = {
            "name": method_name,
            "params": param_list,
            "local_variables": []
        }

        # === Combine local declarations and assignment targets ===

        # Find all local variable declarations inside the function body (<block>)
        local_decls = func.xpath('.//src:block//src:decl', namespaces=ns)
        for decl in local_decls:
            # Get all <src:name> elements (local variable names)
            lnames = decl.xpath('./src:name', namespaces=ns)
            for lname in lnames:
                # Extract the local variable name text
                lname_text = ''.join(lname.xpath('.//text()', namespaces=ns)).strip()
                if lname_text:
                    # Add variable name to local_variables (no filtering for duplicates)
                    func_entry["local_variables"].append(lname_text)

        # Find assignment expressions inside the function body
        func_lhs = func.xpath('.//src:block//src:expr_stmt/src:expr', namespaces=ns)
        for expr in func_lhs:
            # Check if the expression contains an assignment operator "="
            assign_ops = expr.xpath('./src:operator[text()="="]', namespaces=ns)
            if assign_ops:
                # Get the first child of the expression (the LHS of the assignment)
                # LHS = Left-Hand Side
                lhs = expr.xpath('./src:*[1]', namespaces=ns)

                # Make sure that we found a left-hand side node
                if lhs:
                    # extract the text inside the first LHS element
                    lhs_text = ''.join(lhs[0].xpath('.//text()', namespaces=ns)).strip()
                    if lhs_text:
                        # Add the LHS variable name to local_variables
                        func_entry["local_variables"].append(lhs_text)

        # Add this function entry to the list of all functions
        functions_list.append(func_entry)

    # Save all functions into the data list
    data.append({"functions": functions_list})
    
    # === Classes ===
    classes_list = []
    
    def print_class(cls):
        # Dictionary to store data about this class
        cls_data = {}
        # Extract the class name
        cls_data["name"] = ''.join(cls.xpath('./src:name//text()', namespaces=ns)).strip()

        # Prepare lists for attributes and methods and nested classes
        cls_data["attributes"] = []
        cls_data["methods"] = []
        cls_data["nested_classes"] = []
        
        # === Declared attributes ===
        # Select <decl> nodes inside the class body (<block>)
        # Exclude any declarations inside functions, constructors, or destructors.
        # Εnsures we only collect true class fields
        attr_decls = cls.xpath(
            './src:block//src:decl[not(ancestor::src:function or ancestor::src:function_decl '
            'or ancestor::src:constructor or ancestor::src:constructor_decl '
            'or ancestor::src:destructor or ancestor::src:destructor_decl)]',
            namespaces=ns)
        
        # Iterate over each attribute declaration
        for decl in attr_decls:
            # Get all <name> nodes
            names = decl.xpath('./src:name', namespaces=ns)
            for name in names:
                # Extract the name
                name_text = ''.join(name.xpath('.//text()', namespaces=ns)).strip()

                # Save the attribute name
                if name_text:
                    cls_data["attributes"].append(name_text)
    
        # === Attribute assignment expressions ===
        # Find assignment expressions (=) inside the class body (<block>)
        # but not inside functions/constructors/destructors
        attr_exprs = cls.xpath(
            './src:block/src:expr_stmt/src:expr[not(ancestor::src:function or ancestor::src:function_decl '
            'or ancestor::src:constructor or ancestor::src:constructor_decl '
            'or ancestor::src:destructor or ancestor::src:destructor_decl)]',
            namespaces=ns)
        for expr in attr_exprs:
            # Check if the expression contains "="
            assign_op = expr.xpath('./src:operator[text()="="]', namespaces=ns)
            if assign_op:
                # Get left-hand side (attribute being assigned)
                lhs = expr.xpath('./src:*[1]', namespaces=ns)
                if lhs:
                    # Extract the left-hand side (LHS) variable name (i.e. attribute name) of the assignment
                    lhs_text = ''.join(lhs[0].xpath('.//text()', namespaces=ns)).strip()
                    if lhs_text:
                        # Add attribute name to the class attribute list
                        cls_data["attributes"].append(lhs_text)
    
        # === Methods ===
        # Find all functions, constructors, destructors (and their declarations) inside the class
        methods = cls.xpath('./src:block/src:function | ./src:block/src:constructor | '
                            './src:block/src:destructor | ./src:block/src:function_decl | '
                            './src:block/src:constructor_decl | ./src:block/src:destructor_decl',
                            namespaces=ns)
        for method in methods:
            # Get method name
            m_name = ''.join(method.xpath('./src:name//text()', namespaces=ns)).strip()

            # === Get method parameters ===
            # Select all <parameter> nodes inside the parameter list of this method
            params = method.xpath('./src:parameter_list/src:parameter', namespaces=ns)

            # For each parameter, extract only its <name> text.
            # Build a list of parameter names (param_list).
            param_list = [ ''.join(param.xpath('./src:decl/src:name//text()', namespaces=ns)).strip() for param in params ]

            # Prepare a list to collect all local variables of this method
            local_vars = []

            # === Local variables from assignment expressions (expr_stmt) ===
            # Find all assignment expressions (=) inside the method body (<block>)
            exprs = method.xpath('.//src:block//src:expr_stmt/src:expr', namespaces=ns)
            for expr in exprs:
                # Check if the expression contains the assignment operator "="
                assign_op = expr.xpath('./src:operator[text()="="]', namespaces=ns)
                if assign_op:
                    # Get the left-hand side (LHS) of the assignment (the variable being assigned to)
                    lhs = expr.xpath('./src:*[1]', namespaces=ns)
                    if lhs:
                        # Extract the variable name text
                        lhs_text = ''.join(lhs[0].xpath('.//text()', namespaces=ns)).strip()
                        if lhs_text:
                            # Add this variable name to the list of local variables
                            local_vars.append(lhs_text)

            # === Local variables from declarations ===
            # Find all <decl> nodes inside the method body (<block>)
            decls = method.xpath('.//src:block//src:decl', namespaces=ns)
            for decl in decls:

                # Extract all declared variable names under this declaration
                names = decl.xpath('./src:name', namespaces=ns)
                for name in names:
                    # Extract the the variable's name
                    vname = ''.join(name.xpath('.//text()', namespaces=ns)).strip()
                    if vname:
                        # Add the declared variable name to the list of local variables
                        local_vars.append(vname)

            # Store method info in the class data        
            cls_data["methods"].append({
                "name": m_name,
                "params": param_list,
                "local_variables": local_vars
            })
    
        # === Nested classes ===
        nested_classes = cls.xpath('./src:block/src:class', namespaces=ns)
        for nested in nested_classes:
            cls_data["nested_classes"].append(print_class(nested))
        return cls_data
    # Top-level classes
    top_classes = root.xpath(
        './/src:class[not(ancestor::src:class)]',
        namespaces=ns
    )
    for cls in top_classes:
        classes_list.append(print_class(cls))

    # Save all classes information to the data list
    data.append({"classes": classes_list})

    # === Finding comments ===
    comments_list = []
    comments = root.xpath('//src:comment', namespaces=ns)
    for comment in comments:
        comment_text = comment.text.strip()
        if comment_text:
            comments_list.append(comment_text)

    # New JSON only for comments, without adding it to the data list.
    comments_json = [{
        "file": os.path.basename(file_path),
        "comments": comments_list
    }]
    
    return data, comments_json
    
def analyze_folder(folder_path, output_file_path, comments_file_path):
    # List for all analysis results
    all_data = []
    # List for all extracted comments (separate from main data)
    all_comments = []

    # Recursively find all XML files in the folder
    for full_path in Path(folder_path).rglob("*.xml"):
        file = full_path.name
        try:
            # Analyze the XML file -> returns (data, comments)
            file_data, file_comments = analyze_xml_file(str(full_path))
            all_data.append(file_data)
            all_comments.extend(file_comments)
        except Exception as e:
            # If analysis fails, record the error in both JSON structures
            all_data.append([{"file": file}, {"error": str(e)}])
            all_comments.append({"file": file, "comments": [str(e)]})

    # Save full analysis results
    with open(output_file_path, 'w', encoding='utf-8') as out_file:
        json.dump(all_data, out_file, indent=2, ensure_ascii=False)

    # Save only comments in a separate JSON
    with open(comments_file_path, 'w', encoding='utf-8') as comment_file:
        json.dump(all_comments, comment_file, indent=2, ensure_ascii=False)
        
    print(f"Analysis complete. Results saved to: {output_file_path}")
    print(f"Comments JSON saved to: {comments_file_path}")


def run_java_parser(codebase_dir: str, output_dir: str | None = None, srcml_bin: str | None = None) -> tuple[Path, Path]:
    
    """
    Reads all .java files from a local folder,
    converts them into srcML XML (each file becomes <basename>.<ext>.xml),
    then calls analyze_folder(...) to parse and extract information.
    Returns a tuple: (output_json, comments_json).
    """

    # Select srcML executable: given path or from environment (default: "srcml")
    srcml = srcml_bin or os.getenv("SRCML", "srcml")

    # Resolve absolute paths
    codebase_root = Path(codebase_dir).resolve()
    if output_dir is None:
        # Pick base tmp dir
        base_tmp = Path(os.getenv("KG_TMP_BASE", tempfile.gettempdir()))
        # Build the default output folder path: <tmp>/kg_api_cpp/cpp/<project_name>
        output_dir = base_tmp / "kg_api_java" / "java" / codebase_root.name

    # Main output folder for analysis results 
    # and subfolder for srcML XMLs
    out_root = Path(output_dir).resolve()
    xml_root = out_root / "srcml"

    # Create folders if they don’t exist
    out_root.mkdir(parents=True, exist_ok=True)
    xml_root.mkdir(parents=True, exist_ok=True)

    # Collect .java files by extension
    java_files = [p for p in codebase_root.rglob("*.java")]
    if not java_files:
        raise RuntimeError(f"Not found java files in {codebase_root}")

    # Convert each source file to srcML XML
    # Output XML is stored as basename.extension.xml
    for src_path in java_files:
        rel = src_path.relative_to(codebase_root)
        xml_path = (xml_root / rel).with_suffix(rel.suffix + ".xml")
        xml_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [srcml, str(src_path), "--language", "Java", "-o", str(xml_path)]
        try:
            # Run srcML conversion
            subprocess.run(cmd, check=True)
            print(f"[srcML] {src_path}  ->  {xml_path}")
        except subprocess.CalledProcessError as e:
            print(f"[srcML][ERROR] {src_path}: {e}", file=sys.stderr)

    # Run the analyzer on all XML files
    output_json   = out_root / "static_analysis_output_java_lang.json"
    comments_json = out_root / "comments_only_java_lang.json"

    analyze_folder(str(xml_root), str(output_json), str(comments_json))

    print(f"[DONE] JSON: {output_json}")
    print(f"[DONE] Comments: {comments_json}")
    return output_json, comments_json


