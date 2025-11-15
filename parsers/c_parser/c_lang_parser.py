import os
import sys
import subprocess
from lxml import etree  # The etree from lxml is used to parse the XML file.
from collections import defaultdict
import json
import tempfile
from pathlib import Path

ns = {
    # all tags without a prefix (e.g., <unit>, <function>, <decl>) belong to this namespace
    'src': 'http://www.srcML.org/srcML/src',

    # all tags with a prefix (e.g., <cpp:include>, <cpp:directive>, <cpp:file>) belong to this namespace
    'cpp': 'http://www.srcML.org/srcML/cpp'
}

def get_full_context_path(elem):

    # List that will store the "context path"
    context = []
    # Start from the current element and go upwards in the XML tree
    while elem is not None:
        # Get the tag name without the namespace (e.g., "function", "sruct")
        tag = etree.QName(elem).localname

        # If the element is a struct
        if tag =='struct':
            # Extract the text inside <src:name> (this is the struct name)
            name = ''.join(elem.xpath('./src:name//text()', namespaces=ns)).strip()
            # Add "class:Name" to the context list
            # structs are treated as classes for the purposes of static analysis
            # (Because i want the same json for every parser)
            context.append(f'class:{name}')

        # If the element is a function
        elif tag == 'function':
            # Extract the function name from <src:name>
            name = ''.join(elem.xpath('./src:name//text()', namespaces=ns)).strip()
            # Add "function:Name"
            context.append(f'function:{name}')

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

    # === Includes ===
    # In this list, i will save all the includes of a source code file.
    imports_list = []
    # .//cpp:include ---> starts from the root and searches through the entire XML file to find <cpp:include>.
    # cpp:include ---> searches for elements with the <include> tag and the cpp prefix.
    # Therefore, in this case, the namespace is 'http://www.srcML.org/srcML/cpp'.
    # The variable 'includes' contains all the <cpp:include> elements.
    includes = root.xpath('.//cpp:include', namespaces=ns)
    for inc in includes:
        # inc.xpath('.//cpp:file//text()', namespaces=ns) ---> starts from <cpp:include> and looks for <cpp:file>.
        # Once <cpp:file> is found, text() is used to get its content.
        # The content of <cpp:file> is the name of the library being included in the code.
        file = ''.join(inc.xpath('.//cpp:file//text()', namespaces=ns)).strip()
        # For example, inc.xpath(...) returns ['<iostream>']
        # Then join() and strip() are used so that file = <iostream>
        imports_list.append(file)

    # Save the list of all includes in the data list
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

            # If the declaration is inside one of these (function, struct, ...),
            # then it is NOT a global variable
            if tag in ('function', 'function_decl', 'struct'):
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
    # from the root I go to <function> or <function_decl>.
    # Here I have ns = 'http://www.srcML.org/srcML/src'
    functions = root.xpath('.//src:function | .//src:function_decl', namespaces=ns)

    # Iterate over each function element found
    for func in functions:
        # Get the function name
        function_name = ''.join(func.xpath('./src:name//text()', namespaces=ns)).strip()
    
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
            "name": function_name,
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
    
    # === Structs ===
    # structs are treated as classes for the purposes of static analysis
    classes_list = []

    # Find all <class> and <struct> elements in the XML
    classes = root.xpath('.//src:struct', namespaces=ns)
    for cls in classes:

        # Dictionary to store data about this struct
        cls_data = {}

        # Extract the struct name
        cls_data["name"] = ''.join(cls.xpath('./src:name//text()', namespaces=ns)).strip()

        # Prepare lists for attributes
        cls_data["attributes"] = []
        
        # === Declared attributes ===
        # Select <decl> nodes inside the struct body (<block>)
        # Exclude any declarations inside functions.
        # Εnsures we only collect true struct fields
        attr_decls = cls.xpath(
    './src:block//src:decl[not(ancestor::src:function or ancestor::src:function_decl)]',
    namespaces=ns)
        
        # Iterate over each attribute declaration
        for decl in attr_decls:
            # Get all <name> nodes
            names = decl.xpath('./src:name', namespaces=ns)
            for name in names:
                # Extract the name
                name_text = ''.join(name.xpath('.//text()', namespaces=ns)).strip()
                
                # Save ONLY the attribute name (type/init could also be stored if needed)
                if name_text:
                    cls_data["attributes"].append(name_text)
        
        # === Attribute assignment expressions ===
        # Find assignment expressions (=) inside the struct body (<block>)
        # but not inside functions.
        attr_exprs = cls.xpath(
    './src:block//src:expr_stmt/src:expr[not(ancestor::src:function or ancestor::src:function_decl)]',
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
        
        # Add this class(i.e. struct) data to the classes list
        classes_list.append(cls_data)

    # Save all classes(i.e. all structs) information to the data list
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

def run_c_parser(codebase_dir: str, output_dir: str | None = None, srcml_bin: str | None = None) -> tuple[Path, Path]:
    
    """
    Reads all .c/.h files from a local folder,
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
        base_tmp = Path(os.getenv("KG_TMP_BASE", r"C:\kg_tmp"))
        # Build the default output folder path: <tmp>/kg_api_c_lang/c/<project_name>
        output_dir = base_tmp / "kg_api_c_lang" / "c" / codebase_root.name

    # Main output folder for analysis results 
    # and subfolder for srcML XMLs
    out_root = Path(output_dir).resolve()
    xml_root = out_root / "srcml"

    # Create folders if they don’t exist
    out_root.mkdir(parents=True, exist_ok=True)
    xml_root.mkdir(parents=True, exist_ok=True)

    # Collect .c files by extension
    c_files: list[Path] = [p for p in codebase_root.rglob("*.c")]
    if not c_files:
        print(f"[C_LANG][WARN] No .c files in {codebase_root} — skipping.", file=sys.stderr)

        # Produce empty artifacts to keep the pipeline happy
        output_json   = out_root / "static_analysis_output_c_lang.json"
        comments_json = out_root / "comments_only_c_lang.json"

        # Create empty jsons
        output_json.write_text("[]", encoding="utf-8")
        comments_json.write_text("[]", encoding="utf-8")

        return output_json, comments_json

    # Convert each source file to srcML XML
    # Output XML is stored as basename.extension.xml
    for c_path in c_files:
        rel = c_path.relative_to(codebase_root)
        xml_path = (xml_root / rel).with_suffix(rel.suffix + ".xml")  # foo.c -> foo.c.xml
        xml_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [srcml, str(c_path), "--language", "C", "-o", str(xml_path)]
        try:
            # Run srcML conversion
            subprocess.run(cmd, check=True)
            print(f"[srcML] {c_path}  ->  {xml_path}")
        except subprocess.CalledProcessError as e:
            print(f"[srcML][ERROR] {c_path}: {e}", file=sys.stderr)

    # Run the analyzer on all XML files
    output_json   = out_root / "static_analysis_output_c_lang.json"
    comments_json = out_root / "comments_only_c_lang.json"

    analyze_folder(str(xml_root), str(output_json), str(comments_json))
    
    # print(f"[DONE] JSON: {output_json}")
    # print(f"[DONE] Comments: {comments_json}")
    return output_json, comments_json

