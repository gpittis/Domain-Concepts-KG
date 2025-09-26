const parser = require('@babel/parser'); // Babel parser: turns JS code into AST
const traverse = require('@babel/traverse').default; // Babel traverse: walk through the AST nodes
const fs = require('fs');
const path = require('path');

// --- Check command line arguments ---
if (process.argv.length < 3) {
  console.error('Usage: node babel_javascript_parser.js <path-to-js-file-or-folder>');
  process.exit(1); // Exit if no input path provided
}

const inputPath = process.argv[2]; // Path of a .js file or a folder with .js files


// --- Helper: recursively find all .js files inside a folder ---
function getJsFiles(dir) {
  let results = [];
  const list = fs.readdirSync(dir); // List all files/folders in directory
  list.forEach(file => {
    const fullPath = path.join(dir, file);
    const stat = fs.statSync(fullPath); // Get file/folder stats
    if (stat && stat.isDirectory()) {
      // If it's a directory , then recurse inside
      results = results.concat(getJsFiles(fullPath));
    } else if (file.endsWith('.js')) {
      // If it's a JS file , then add to results
      results.push(fullPath);
    }
  });
  return results;
}

// --- Collect list of JS files to parse ---
let filesToParse = [];

if (fs.existsSync(inputPath)) {
  const stat = fs.statSync(inputPath);
  if (stat.isDirectory()) {
    filesToParse = getJsFiles(inputPath); // Get all .js files from folder
  } else if (stat.isFile() && inputPath.endsWith('.js')) {
    filesToParse = [inputPath]; // Single file input
  } else {
    console.error('Provided path is neither a .js file nor a directory.');
    process.exit(1);
  }
} else {
  console.error('Path does not exist:', inputPath);
  process.exit(1);
}

const analysis = {}; // Object that will hold the static analysis results per file

// --- Helper: simplify import paths to just the last part (filename) ---
function normalizeImport(source) {
  if (!source || typeof source !== 'string') return source;

  // Split path into parts (support / and \)
  const parts = source.split(/[/\\]+/);
  let last = parts[parts.length - 1] || source;

  // Remove known extensions (.js, .ts, .jsx, etc.)
  last = last.replace(/\.(mjs|cjs|js|ts|tsx|jsx|mts|cts)$/i, '');

  // If filename has dots (e.g. helpers.min.js) keep only the first part
  last = last.split('.')[0];

  return last;
}


// --- Parse each file and extract information ---
filesToParse.forEach(filePath => {
  let code;
  try {
    code = fs.readFileSync(filePath, 'utf8'); // Read JS file content
  } catch (e) {
    console.warn(`[skip][read] ${filePath}: ${e.message}`);
    return; // << skip file, continue
  }

  // Parse file content into AST
  let ast;
  try {
    ast = parser.parse(code, {
    sourceType: 'module', // allow ES modules
    plugins: [ // Enable Babel parser plugins so it can understand extra syntax
      'jsx',
      'typescript',
      'decorators-legacy',
      'classProperties',
      'classPrivateProperties',
      'classPrivateMethods',
      'asyncGenerators',
      'dynamicImport',
      'exportDefaultFrom',
      'exportNamespaceFrom',
      'objectRestSpread'
      ],
    });
  } catch (e) {
    console.warn(`[skip][parse] ${filePath}: ${e.message}`);
    return; // << skip file, continue
  }
  
  // --- Data containers for this file ---
  const imports = [];  // List of imports
  const globalVariables = []; // List of global vars
  const functions = []; // List of functions
  const classes = []; // List of classes
  const exportsList = []; // List of exports

  // Helper: extract all local variables inside a given scope (e.g. function body)
  // - It walks through the AST nodes inside "path"
  // - Finds all VariableDeclaration nodes (e.g. let, const, var)
  // - Collects the variable names and returns them as a list
  function extractLocalVariables(path) {
    const vars = [];
    path.traverse({
      VariableDeclaration(innerPath) {
        if (!innerPath.node.declarations) return;
        innerPath.node.declarations.forEach(decl => {
          if (decl.id?.type === 'Identifier') {
            vars.push(decl.id.name); // Add variable name
          }
        });
      }
    });
    return vars;
  }


  // --- Walk through the AST ---
  try {
    traverse(ast, {
    // --- ES Module imports ---
    // This block runs whenever the parser finds an `ImportDeclaration` node,
    // e.g. in code like:
    //     import fs from 'fs';
    ImportDeclaration(p) {
      if (p.node.source?.value) {
        // add the ImportDeclaration to our list of imports for this file
        imports.push(normalizeImport(p.node.source.value));
      }
    },

    // CommonJS require(...)
    // Catch calls like: require('module-name')
    CallExpression(p) {
      const callee = p.node.callee;
      if (
        callee?.type === 'Identifier' && // must be a Identifier
        callee.name === 'require' && // specifically "require"
        p.node.arguments?.length > 0 && // has at least one argument
        p.node.arguments[0].type === 'StringLiteral'  // first arg is a string
      ) {
        // Add the module name (normalized) to the imports list
        imports.push(normalizeImport(p.node.arguments[0].value));
      }
    },

    // --- Top-level variable declarations (global vars) ---
    VariableDeclaration(path) {
      // Check if this variable declaration is inside a function
      const isInsideFunction = path.getFunctionParent() !== null;
      // If not inside a function , then treat it as "global" (really: top-level in the file/module)
      if (!isInsideFunction && path.node.declarations) {
        path.node.declarations.forEach(decl => {
          if (decl.id?.type === 'Identifier') {
            // Save the variable name into the globalVariables list
            globalVariables.push(decl.id.name);
          }
        });
      }
    },


    // --- Exported values using assignment (exports / module.exports) ---
    AssignmentExpression(path) {
  const node = path.node; // The assignment expression node (LHS = RHS)

  // === Case 1: exports.prop = ... ===
  if (
    node.left?.type === 'MemberExpression' && // LHS must be a property access
    node.left.object?.type === 'Identifier' && // The object is an identifier
    node.left.object.name === 'exports' // That identifier is "exports"
  ) {
    const exportName = node.left.property?.name || node.left.property?.value; // Get property name after "exports."
    const right = node.right; // RHS of assignment
    if (
      right?.type === 'FunctionExpression' ||
      right?.type === 'ArrowFunctionExpression'
    ) {
      functions.push({ // Save as a function export
        name: exportName ? `exports.${exportName}` : 'exports.<unknown>', // function name
        arguments: right.params?.map(p => p.name).filter(n => n), // function params
        localVariables: extractLocalVariables(path) // collect local variables inside function
      });
    } else if (exportName) {
      globalVariables.push(`exports.${exportName}`); // Save as a global variable export
    }
  }

  // === Case 2: module.exports = { ... } ===
  else if (
    node.left?.type === 'MemberExpression' && // LHS must be a property access
    node.left.object?.type === 'Identifier' && // The object is an identifier
    node.left.object.name === 'module' &&  // That identifier is "module"
    node.left.property?.name === 'exports' && // Property is "exports"
    node.right?.type === 'ObjectExpression' // RHS is an object literal
  ) {
    node.right.properties.forEach(prop => {
      if (prop.type === 'ObjectProperty' || prop.type === 'Property') {
        const keyName = prop.key?.name || prop.key?.value; // Get the property name

        // If the value of this property is a function (either a normal function or an arrow function), 
        // then we record it in the functions list.
        if (
          prop.value.type === 'FunctionExpression' ||
          prop.value.type === 'ArrowFunctionExpression'
        ) {
          functions.push({ // Save property as function export
            name: `module.exports.${keyName}`, // Full export name
            arguments: prop.value.params?.map(p => p.name).filter(n => n), // function params
            localVariables: [] // Can't easily get locals here, so empty
          });
        } else {
          globalVariables.push(`module.exports.${keyName}`); // Save property as global variable export
        }
      }
    });
  }

  // === Case 3: module.exports.prop = ... ===
  else if (
    node.left?.type === 'MemberExpression' && // LHS is a property access
    node.left.object?.type === 'MemberExpression' && // Object itself is also a MemberExpression
    node.left.object.object?.name === 'module' && // Outer object is "module"
    node.left.object.property?.name === 'exports' // Its property is "exports"
  ) {
    const exportName = node.left.property?.name || node.left.property?.value; // Property name after module.exports.
    const right = node.right; // RHS of assignment
    if (
      right?.type === 'FunctionExpression' ||
      right?.type === 'ArrowFunctionExpression'
    ) {
      functions.push({ // Save as function export
        name: exportName ? `module.exports.${exportName}` : 'module.exports.<unknown>',  // function name
        arguments: right.params?.map(p => p.name).filter(n => n), // function params
        localVariables: extractLocalVariables(path) // collect local vars
      });
    } else if (exportName) {
      globalVariables.push(`module.exports.${exportName}`); // Save as global variable export
    }
  }
},

    // --- Top-level function declarations (e.g. function foo() {}) ---
    FunctionDeclaration(path) {
      // Check that the function is declared directly at the top level of the file
      // (its parent node is the Program, i.e., the root of the AST)
      if (path.parent?.type === 'Program' && path.node.id?.name) {
        functions.push({ // Save this function in our list
          name: path.node.id.name, // The function's name
          arguments: path.node.params?.map(p => p.name).filter(name => name), // The function's parameter names
          localVariables: extractLocalVariables(path) // Collect any local variables declared inside the function body
        });
      }
    },

    // --- Functions defined as variable initializers ---
    // Example:
    //   const bar = function(x) { ... };
    //   const baz = (y) => y * 2;
    VariableDeclarator(path) {
      if (
        path.node.init &&
        // Arrow function or Function expression
        (path.node.init.type === 'ArrowFunctionExpression' || path.node.init.type === 'FunctionExpression') &&
        path.node.id?.name // The variable has an identifier name
      ) {
        functions.push({  // Save this function in our list
          name: path.node.id.name, // The variable name becomes the function's name
          arguments: path.node.init.params?.map(p => p.name).filter(name => name), // The parameter names of the function
          localVariables: extractLocalVariables(path) // Collect local variables declared inside this function
        });
      }
    },

    // --- Class declarations ---
    ClassDeclaration(path) {
      const clsName = path.node.id?.name;
      if (!clsName) return; // Ignore if class name dont exist

      // Prepare a structure to hold the class info
      const cls = {
        name: clsName, // Class name
        attributes: [], // Properties / fields of the class
        methods: [] // Methods (constructor, functions, static methods, etc.)
      };

      // Traverse inside the class body to extract methods and properties
      path.traverse({

        // --- Class methods ---
        ClassMethod(methodPath) {
          if (!methodPath.node.key?.name) return; // Skip if the method has no name

          // If it's a constructor, use "constructor" as the name
          // Otherwise take the method's key (e.g., "doSomething")
          const methodName = methodPath.node.kind === 'constructor' ? 'constructor' : methodPath.node.key.name;

          // Collect the argument names of the method
          const args = methodPath.node.params?.map(p => p.name).filter(name => name) || [];

          // Collect local variables declared inside the method
          const localVars = extractLocalVariables(methodPath);

          // --- Special case: constructor ---
          // Inside constructors, look for assignments like "this.x = ..."
          // These reveal the attributes (fields) of the class
          if (methodName === 'constructor') {
            methodPath.traverse({
              AssignmentExpression(assignPath) {
                const a = assignPath.node;
                if (
                  a.left?.type === 'MemberExpression' && // e.g., "this.x"
                  a.left.object?.type === 'ThisExpression' && // object must be "this"
                  a.left.property?.type === 'Identifier' // property is a normal identifier
                ) {
                  cls.attributes.push(a.left.property.name); // Add "x" to attributes
                }
              }
            });
          }

          // Add this method to the methods list
          cls.methods.push({
            name: methodName, // method name or "constructor"
            arguments: args, // parameter names
            localVariables: localVars, // locals inside the method
            static: methodPath.node.static || false // true if it's a static method
          });
        },

        // --- Class properties (fields) ---
        ClassProperty(propPath) {
          if (!propPath.node.key) return; // Skip if no key

          // Handle normal vs private fields
          const name = propPath.node.key.type === 'PrivateName'
            ? `#${propPath.node.key.id?.name || ''}`
            : propPath.node.key.name || '';
          if (!name) return; // If still no name, skip

          // If the property value is an arrow function, treat it as a method
          if (propPath.node.value?.type === 'ArrowFunctionExpression') {
            cls.methods.push({
              name, 
              arguments: propPath.node.value.params?.map(p => p.name).filter(name => name) || [],
              localVariables: extractLocalVariables(propPath),
              static: propPath.node.static || false
            });
          } else { // Otherwise, treat it as a simple attribute/field
            cls.attributes.push(name);
          }
        }
      });
      // After collecting methods and attributes, add this class to the list
      classes.push(cls);
    },

    // --- Named exports: `export function foo(...) { ... }` or `export class X { ... }` etc.
    ExportNamedDeclaration(path) {
  if (!path.node.declaration) return;

  const decl = path.node.declaration; // The actual thing being exported (function/class/var...)
  const declPath = path.get('declaration'); // A path handle so we can traverse inside the declaration

  // We only handle: `export function foo(...) { ... }`
  if (decl.type === 'FunctionDeclaration' && decl.id?.name) {
    // Record this function in the functions list (name, params, local vars)
    functions.push({
      name: decl.id.name, // function name
      arguments: decl.params?.map(p => p.name).filter(n => n), // parameter names
      localVariables: extractLocalVariables(declPath.get('body')) // local variables
    });

    // Also note the fact that a named function was exported
    exportsList.push(`function ${decl.id.name}`);
  }
},
    // --- Default exports: `export default ...`
    ExportDefaultDeclaration(path) {
      const decl = path.node.declaration; // What is being exported by default
      if (!decl) return;

      // export default class
      if (decl.type === 'ClassDeclaration') {
        exportsList.push(`default class ${decl.id?.name || '(anonymous)'}`);
      } 
      // export default function
      else if (decl.type === 'FunctionDeclaration') {
        exportsList.push(`default function ${decl.id?.name || '(anonymous)'}`);
      } else {
        exportsList.push('default export (expression)');
      }
    }
     });
  } catch (e) {
    console.warn(`[skip][traverse] ${filePath}: ${e.message}`);
    return; // << skip file, continue
  }


  const relativePath = path.relative(inputPath, filePath).replace(/\\/g, '/');

  analysis[relativePath] = { // These arrays were populated while traversing the AST above
  imports, // normalized import/require targets used by this file
  globalVariables, // vars declared at top-level (module scope)
  functions, // functions found (declared or assigned), with params and local vars
  classes, // classes with attributes and methods
  exports: exportsList // summary of "export ..." statements
  };
});

// --- Write all results to a JSON file ---
const outputPath = path.join(inputPath, 'javascript_codebase_ast_analysis.json');
fs.writeFileSync(outputPath, JSON.stringify(analysis, null, 2));
console.log(`Analysis complete for ${filesToParse.length} files. Output saved to ${outputPath}`);
