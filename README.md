# Domain-Concepts-KG
Domain Concepts Knowledge Graph (**Structured Graph** + **Knowledge Graph**) created by static analysis


## Structured Graph

[c_lang_parser.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/c_lang_parser.py) : είναι ο parser για C codebases

[cpp_parser.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/cpp_parser.py) : είναι ο parser για C++ codebases

[java_parser.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/java_parser.py) : είναι ο parser για Java codebases

[python_parser.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/python_parser.py) : είναι ο parser για Python codebases

[babel_javascript_parser.js](https://github.com/gpittis/Domain-Concepts-KG/blob/main/babel_javascript_parser.js) : είναι ο parser για Javascript codebases

[python_wrapper_for_js_parser.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/python_wrapper_for_js_parser.py) : είναι ο python wrapper που καλεί τον javascript parser και εκτελεί την ανάλυση

Ολοι οι **parsers** βρίκσουν :
- File name
- Imports
- Global Variables
- Functions with parameters and local variables
- Classes with attributes and methods
- Class Methods with parameters and local variables
- Comments

Ο **python parser** βρίσκει επιπλέον nested classes και nested functions.

Οι **c και cpp parsers** βρίσκουν επιπλέον nested classes και nested functions , όμως δεν μπορούν να καταλάβουν το scope στο οποίο βρίσκονται αυτες οι nested δομές. 
Επομένως, χειρίζονται τις nested classes και nested functions ως top-level Functions και Classes. Έκανα πάρα πολλές προσπάθειες για να το βελτιώσω αυτό αλλά δε τα κατάφερα.

Ο **java parser** βρίσκει επιπλέον nested classes. 

Ο **javascript parser** ΔΕΝ βρίσκει nested functions/classes.

Δοκίμασα τους parsers σε αληθινά codebases και έμεινα αρκετά ευχαριστημένος από τα αποτελέσματα.

Όλοι οι parsers παράγουν JSON με το ίδιο format. Πιο συγκεκριμένα, έχουν το ίδιο βασικό format :

```
      [
        {"file": ...},
        {"imports": [...]},
        {"global_variables": [...]},
        {"functions": [...]},
        {"classes": [...]}
      ]
```

Για τις ανάγκες της στατικής ανάλυσης, τα structs (σε c, cpp)  αντιμετωπίστηκαν ως classes. (Προκειμένου όλοι οι parsers να παράγουν json με ίδιο format)

---
**Concept Filter** :

[stopwords_filter.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/stopwords_filter.py)

- Δέχεται ως είσοδο το JSON που παράχθηκε από τον parser.

- Καθαρίζει/φιλτράρει όλα τα strings του JSON (χωρίς να αλλάξει το σχήμα του) ώστε να μείνουν μόνο λέξεις/φράσεις με domain specific context.

- Δουλεύει αναδρομικά σε όλο το JSON αντικείμενο (dicts, lists, strings) και επιστρέφει JSON ίδιου σχήματος με “καθαρισμένα” strings.

- Φορτώνει τα περιεχόμενα από 4 jsons που περιέχουν common code words και stop words. Με αυτόν τον τρόπο δημιουργει το set STOPWORDS. Το set STOPWORDS χρησιμοποιειται για το φιλτραρισμα των strings.

- Τα 4 επιμέρους json είναι :

[common_code_words_manually_collected.json](https://github.com/gpittis/Domain-Concepts-KG/blob/main/common_code_words_manually_collected.json)

[common_verbs_list.json](https://github.com/gpittis/Domain-Concepts-KG/blob/main/common_verbs_list.json)

[nltk_english_stopwords.json](https://github.com/gpittis/Domain-Concepts-KG/blob/main/nltk_english_stopwords.json)

[stopwords_list_from_stopwords_iso_github_repo.json](https://github.com/gpittis/Domain-Concepts-KG/blob/main/stopwords_list_from_stopwords_iso_github_repo.json)

(τις πηγές των jsons τις αναφέρω στο stopwords_filter.py. Το chat gpt μου έδωσε κάποιες πολύ κοινές λέξεις που αποτελούν infrastructure σε πάρα πολλά codebases ανεξάρτητα από το domain που έχουν)


- Κανόνες tokenization / split :

  - Διαχωρισμός CamelCase/PascalCase & ακρωνύμιων (π.χ. HTTPServer → HTTP Server, createdAt → created At).

  - Διαχωρισμός σε _ - . (π.χ. foo_bar-baz.qux → foo bar baz qux).

  - Διαχωρισμός χαρακτήρων/ψηφίων (π.χ. var1 → var 1, variable1X → variable 1 X).

  - Μετατροπή όλων των non-word characters σε spaces

- Κανόνες φιλτραρίσματος

  - Αγνοεί tokens με μήκος < 3

  - Αγνοεί tokens που είναι αμιγώς αριθμητικά (π.χ. 2024)

  - Αγνοεί tokens που είναι hex-like μορφής 0x[0-9a-f]+

  - Αγνοεί ΟΛΑ τα tokens που περιλαμβάνονται στο set STOPWORDS(δες παραπάνω).

  - Μετά το φιλτράρισμα, αφαιρεί διαδοχικά duplicates (π.χ. robot robot arm → robot arm).

---

**Create Knowledge Graph (KG) JSON**

[json_creation_for_neo4j.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/json_creation_for_neo4j.py)

Δέχεται ως είσοδο ένα cleaned JSON (που παράχθηκε από το concept filter) και παράγει ένα Knowledge Graph JSON που περιέχει:

- Nodes για repos, files, imports, global variables, classes, functions, nested classes, nested functions, methods, parameters, local variables, attributes. Επομένως, έχω τα ακόλουθα node types :
  - REPO
  - FILE
  - IMPORT
  - GLOBAL_VAR
  - CLASS
  - NESTED_CLASS
  - FUNCTION
  - NESTED_FUNCTION
  - METHOD
  - PARAM
  - LOCAL_VAR
  - ATTRIBUTE

- Relationships που συνδέουν τα nodes. Επομένως, έχω τα ακόλουθα relationships types :
  - FILE -[**EXISTS_IN**]-> REPO
  - FILE -[**FILE_CONTAINS**]-> CLASS/FUNCTION
  - FILE -[**IMPORTS**]-> IMPORT
  - FILE -[**HAS_GLOBAL_VAR**]-> GLOBAL_VAR
  - CLASS -[**HAS_ATTRIBUTE**]-> ATTRIBUTE
  - CLASS -[**HAS_METHOD**]-> METHOD
  - FUNCTION/METHOD -[**HAS_PARAM**]-> PARAM
  - FUNCTION/METHOD -[**HAS_LOCAL_VAR**]-> LOCAL_VAR
  - FUNCTION/METHOD -[**HAS_NESTED_FUNCTION**]-> NESTED_FUNCTION
  - CLASS/FUNCTION -[**HAS_NESTED_CLASS**]-> NESTED_CLASS

- Weights σε nodes και relationships, ώστε να κωδικοποιούνται οι προτεραιότητες με DSL-oriented λογική και επιπλέον να γίνεται πιο εύκολο το querying. Πιο συγκεκριμένα, έχω :
  - NODE WEIGHTS :
    - "REPO": 0.10
    - "FILE": 0.55
    - "IMPORT": 0.65
    - "GLOBAL_VAR": 0.70 
    - "CLASS": 0.95
    - "NESTED_CLASS": 0.70
    - "FUNCTION": 0.90
    - "NESTED_FUNCTION": 0.70
    - "METHOD": 0.85
    - "PARAM": 0.60
    - "LOCAL_VAR": 0.50
    - "ATTRIBUTE": 0.70

**Core structures : (weight >= 0.85)**

Έχω δώσει πολύ μεγάλα βάρη στα CLASS/FUNCTION/METHOD nodes, διότι αυτές οι δομές αποτελούν τον σκελετό κάθε προγράμματος και είναι ιδιαίτερα σημαντικά από τη σκοπιά της στατικής ανάλυσης. 
Επίσης, αποτελούν και τον πυρήνα των DSLs που θα παραχθούν από το Knowledge Graph, διότι τα CLASS nodes αποτελούν entities και τα FUNCTION/METHOD nodes δηλώνουν συγκεκριμένα actions/behaviors. Οπότε, αυτά σε πρώτη φάση μπορούν να φτιάξουν τον πυρήνα μιας DSL.

**Attributes : (weight = 0.7)**

Είναι οι ιδιότητες των classes στην στατική ανάλυση. Επομένως, θα είναι οι ιδιότητες/properties των entities σε μια DSL. Εμπλουτίζουν σημαντικά τον σκελετό μιας DSL.

**global variables : (weight = 0.7)**

Είναι μεταβλητές που ορίζονται σε επίπεδο αρχείου. Επομένως έχουν πρόσβαση σε αυτές όλα τα funcions και classes του αρχείου. Μπορεί να μαρτυρούν μια "κοινόχρηστη" κατάσταση μεταξύ των functions και classes σε ένα αρχείο. 

**Nested Classes / Nested Functions (weight = 0.70 + decay factor) :**

Αποτελούν sub-entities που δεν στέκονται αυτόνομα αλλά εξαρτώνται από το parent class/function. Παίρνουν αρχικό βάρος 0.70 όταν βρίσκονται σε πρώτο επίπεδο nesting (μέσα σε top-level class ή function).
Αν βρίσκονται βαθύτερα (δηλαδή το parent class/function είναι και αυτο nested), τότε εφαρμόζεται decay factor (LAMBDA_DECAY) ώστε το βάρος να μειώνεται εκθετικά.
Επομένως, αναγνωρίζω τις nested functions/classes ως σημαντικές λεπτομέρειες, αλλά δίνω τη μεγάλη βαρύτητα στα top-level class/functions.


Στα υπόλοιπα nodes αποδόθηκαν αντίστοιχα βάρη ανάλογα με τη σημαντικότητά τους. Όλα τα βάρη είναι σχετικά υψηλά, καθώς κάθε τύπος κόμβου μπορεί να περιέχει domain-specific πληροφορία που δεν πρέπει να αγνοηθεί. Με αυτήν την επιλογή βαρών δίνεται έμφαση στα πιο core DSL nodes (π.χ. Class, Function, Method, Attribute), αλλά ταυτόχρονα λαμβάνονται υπόψη και τα πιο δευτερεύοντα nodes (π.χ. Local_var, Param) ώστε να διατηρηθεί μια ισορροπημένη εικόνα του domain.

Τέλος, το node REPO δεν περιέχει domain specific context. Το έφτιαξα για να μπορέσω να συνδέσω όλα τα files μεταξύ τους.

 - EDGE_WEIGHTS :
   - "EXISTS_IN": 0.30
   - "FILE_CONTAINS": 0.90
   - "IMPORTS": 0.70
   - "HAS_GLOBAL_VAR": 0.70
   - "HAS_ATTRIBUTE": 0.70
   - "HAS_METHOD": 0.90
   - "HAS_PARAM": 0.65
   - "HAS_LOCAL_VAR": 0.50
   - "HAS_NESTED_FUNCTION": 0.70
   - "HAS_NESTED_CLASS": 0.70

Η λογική που ακολουθώ με τα βάρη των relationships είναι παρόμοια με παραπάνω. Τα **FILE_CONTAINS**,  **HAS_METHOD** εμπλέκουν τα FUNCTIONS/CLASSES/METHODS των codebases. Δηλαδή, περιέχουν τον πυρήνα των DSLs και για τον λόγο αυτό έχουν πολύ υψηλά βάρη. Ακολουθούν τα **HAS_ATTRIBUTE**, **HAS_GLOBAL_VAR**, **IMPORTS**, **HAS_NESTED_FUNCTION**, **HAS_NESTED_CLASS** που περιέχουν domain specific λεπτομέρειες ώστε να εμπλουτίσουν τον πυρήνα της DSL. Οι υπόλοιπες relationships έχουν χαμηλότερα βάρη.


**Δομή node**

Περιέχει :
- τύπο node
- όνομα node
- βάρος node
- βάθος node (0 αν ειναι top-level , >=1 αν ειναι nested)


**Δομή relationship**

Περιέχει :
- τύπο relationship
- όνομα node από τον οποίο φεύγει το relationship
- όνομα node στον οποίο καταλήγει το relationship
- τύπο node από τον οποίο φεύγει το relationship
- τύπο node στον οποίο καταλήγει το relationship
- βάρος node από τον οποίο φεύγει το relationship (το ονομάζω from_w)
- βάρος node στον οποίο καταλήγει το relationship (το ονομάζω to_w)
- βάρος relationship  (edge_base)
- τελικό βάρος relationship (final_weight) = (from_w + to_w + edge_base)/3 
           
**Το τελικό βάρος του relationship υπολογίζεται με μέσο όρο. Με αυτόν τον τρόπο χειρίζομαι ισότιμα όλα τα βάρη που υπάρχουν στο relationship.**

**Στο DeepGit , ο δημιουργος χρησιμοποιει σταθμισμένο άθροισμα : final_score = a * score_1 + b * score_2 + ..**

**Στο DeepGit μερικά από τα scores προκύπτουν από εκπαιδευμένα NLP μοντέλα, ενώ άλλα είναι repository-level metrics (π.χ. stars, activity, code quality). Στη συνέχεια, ο δημιουργός ανάλογα με τον σκοπό του , αποφασίζει τη σειρά σημαντικότητας των scores. Έτσι, πολλαπλάσιαζει το κάθε επιμέρους score με ένα συντελεστή (π.χ. a, b, ..). Αυτοί οι συντελεστές είναι τα βάρη.**

**Στην δικιά μου περίπτωση, πιστεύω πως το σταθμισμένο άθροισμα θα χαλούσε τα αποτελέσματα. Αυτό γιατί η επιλογή των βαρών όλων των nodes και των relationships έγινε με DSL-oriented λογική. Άρα, ο extra πολλαπλασιασμός με έναν αυθαίρετο συντελεστή είναι και περιττός και επικίνδυνος να χαλάσει τον διαχωρισμό που όρισα μεταξύ των nodes και των relationships.**


- Με βάση τα final_weights των relationships που προκύπτουν με τον τύπο (from_w + to_w + edge_base)/3 , έχουμε :
  - FILE -[**EXISTS_IN**]-> REPO
    - **final_weight = 0.316667**
 
  - FILE -[**FILE_CONTAINS**]-> CLASS
    - **final_weight = 0.8**
    
  - FILE -[**FILE_CONTAINS**]-> FUNCTION
    - **final_weight = 0.783333**
    
  - FILE -[**IMPORTS**]-> IMPORT
    - **final_weight = 0.633333**
    
  - FILE -[**HAS_GLOBAL_VAR**]-> GLOBAL_VAR
    - **final_weight = 0.65**
    
  - CLASS -[**HAS_ATTRIBUTE**]-> ATTRIBUTE
    - **final_weight = 0.783333**
    
  - CLASS -[**HAS_METHOD**]-> METHOD
    - **final_weight = 0.9**
    
  - FUNCTION -[**HAS_PARAM**]-> PARAM
    - **final_weight = 0.716667**
    
  - METHOD -[**HAS_PARAM**]-> PARAM
    - **final_weight = 0.7**
    
  - FUNCTION -[**HAS_LOCAL_VAR**]-> LOCAL_VAR
    - **final_weight = 0.63333**
    
  - METHOD -[**HAS_LOCAL_VAR**]-> LOCAL_VAR
    - **final_weight = 0.616667**
   
Με αντίστοιχο τρόπο και για τις nested functions/classes

  --- 
- **ΚΑΝΟΝΕΣ querying με τα final_weights των relationships**
  - **final_weight >= 0.8**  (the core of DSL) 
    - Παίρνω CLASSES και METHODS
      
  - **final_weight >= 0.75** (the full skeleton of DSL)
    - Παίρνω CLASSES , METHODS , FUNCTIONS, ATTRIBUTES
      
  - **final_weight >= 0.7** 
    - Παίρνω CLASSES , METHODS , FUNCTIONS, ATTRIBUTES, FUNCTION PARAMS, METHOD PARAMS
      
  - **final_weight >= 0.6**
    - Τα παίρνω όλα
---

**Κατά την εφαρμογή του concept filter , παρατήρησα ότι προέκυψαν CLASSES με κενά ονόματα αλλά συνέχιζαν να περιέχουν attributes και methods χωρίς κενά ονόματα.**

**Επίσης, παρατήρησα ότι προέκυψαν FUNCTIONS με κενά ονόματα αλλά συνέχιζαν να περιέχουν parameters και local variables χωρίς κενά ονόματα.**

**Επομένως, αν αγνούσα αυτές τις περιπτώσεις κατά την δημιουργία του Knowledge Graph JSON , τότε πρακτικά θα έχανα κάποια domain specific πληροφορία. Για τον λόγο αυτό, αποφάσισα να κρατήσω τέτοια CLASSES και FUNCTIONS που περιέχουν τουλάχιστον 1 στοιχείο με μη κενό όνομα. Σε αυτά τα CLASSES και FUNCTIONS δίνω ένα συνθετικό όνομα. Όλα αυτα τα ονόματα ξεκινούν με τον ίδιο τρόπο ανάλογα με τον τύπο του node (δηλαδή FILE_ANON_ , CLASS_ANON_ , FUNCTION_ANON_). Οπότε, μπορώ πολύ εύκολα να τα εξαιρέσω από τα αποτελέσματα της αναζητησης στο KG με κατάλληλα queries.**

Αν δεν θέλω καθόλου τετοια CLASSES και FUNCTIONS με συνθετικό όνομα, μπορώ να γράψω κατάλληλα ερωτήματα όπως :
```
MATCH (a)-[r]->(b)
WHERE r.final_weight >=0.7
  AND NOT a.name =~ "^(FILE|CLASS|REPO|FUNCTION|METHOD|NESTED_CLASS|NESTED_FUNCTION)_ANON_.*"
  AND NOT b.name =~ "^(FILE|CLASS|REPO|FUNCTION|METHOD|NESTED_CLASS|NESTED_FUNCTION)_ANON_.*"
RETURN a, r, b
```

Ακόμη μπορώ να τα διαγράψω πολύ εύκολα :
```
MATCH (n)
WHERE n.name =~ "^(FILE|CLASS|FUNCTION|METHOD|NESTED_CLASS|NESTED_FUNCTION)_ANON_.*"
DETACH DELETE n
```

**Αυτό το κρατάμε στο structure graph και το αφαιρούμε στο knowledge graph**

---

Από την έρευνα που έκανα δεν βρήκα paper ή github repo που να φτιάχνει knowledge graph με δεδομένα στατικής ανάλυσης και να χρησιμοποιεί βάρη. Υπάρχουν κάποιοι KG που περιέχουν δεδομένα στατικής ανάλυσης αλλά ΔΕΝ περιέχουν βάρη. Ένα ενδεικτικό paper είναι : [paper](https://ieeexplore.ieee.org/document/10019850)

---

**Load to Structured Graph**

[loader_script.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/loader_script.py)

Αυτό το script φορτώνει το Structured Graph JSON μέσα σε μια βάση Neo4j.

Για κάθε node και relationship δημιουργούνται μοναδικά node/relationships αντίστοιχα με χρήση MERGE, ώστε να αποφεύγονται διπλότυπα.

Επιπλέον υπολογίζεται το normalized_appearances για nodes και relationships :
  - normalized_appearances για nodes : πλήθος εμφανίσεων κόμβου / συνολικό πλήθος κόμβων
  - normalized_appearances για relationships : πλήθος εμφανίσεων relationship / συνολικό πλήθος relationships
 
Για τα synthetic names (ANON nodes) κανονικοποιούνται με namespace που παράγεται από το repo_url ώστε να μην έχω collisions με διαφορετικά repos.

---

**Knowledge Graph JSON created by Structured Graph**

Το αρχείο [knowledge_graph_define_json.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/knowledge_graph_define_json.py) ορίζει τα nodes και τα relationships του Knowledge Graph. Πιο συγεκριμένα κάνει τα εξής :

1. Συνδέεται στον Structured Graph
   
2. Στέλνει query στον Structured Graph και λαμβάνει τα type , τα names και τα weights όλων των nodes που υπάρχουν μέσα στο Structured Graph, ΕΚΤΟΣ από εκείνα που έχουν type REPO, έχουν synthetic name (e.g. __ANON__) ή empty/NULL name. (query stored in **CYPHER_NODES** variable).
   
3. Στέλνει query στον Structured Graph και λαμβάνει το source_node_name , το target_node_name και το final_weight για κάθε relationship μέσα στο Structured_Graph. Εξαιρούνται τα relationships που περιέχουν nodes με REPO type, empty/NULL name ή synthetic name (e.g. __ANON__). (query stored in **CYPHER_RELS** variable).

4. Χρησιμοποιεί τον **nltk Snowball Stemmer** και κάνει steme τα names όλων των structured nodes.

5. Σπάει τα structured node names που περιέχουν >=2 words σε μεμονωμένα words/tokens. Για παράδειγμα, αν στο Structured Graph έχω node("render img") , τότε στο Knowledge Graph θα έχω 2 nodes με names "render" και "img" αντίστοιχα.

6. Ακόμη, χρησιμοποιεί ένα Helper function για να κάνει **αλφαβητική κανονικοποίηση** των νέων nodes μέσα στα relationships. Για παράδειγμα, στο Structured Graph μπορεί να έχω σε κάποιο σημείο **robot --> sensor** και κάπου αλλού να έχω **sensor --> robot**. Αν δεν υπήρχε αυτός ο Helper τότε στο Knowledge Graph θα δημιουργούνταν 2 relationships που πρακτικά σημαίνουν το ίδιο πράγμα. Επομένως, πλέον γίνεται κανονικοποίηση (**robot < sensor**) και έτσι στο KG θα έχω πάντα **robot --> sensor με άθροιση των επιμέρων βαρών**.

---
**API**

[api.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/api.py)

Αυτοματοποιεί όλη την διαδικασία : parsing github repo + concept filter + create KG JSON + Load to Neo4j 

 - Λήψη GitHub repo (μέσω Github REST API)

 - Unzip & προετοιμασία τοπικού workspace σε προσωρινό φάκελο.

 - Parsing του κώδικα με language-specific parser
   - cpp (1)
   - c (2)
   - python (3)
   - java (4)
   - javascript (5)

 - Concept filter για καθαρισμό και φιλτράρισμα domain specific εννοιών

 - Knowledge Graph builder JSON : μετατροπή σε ενδιάμεσο JSON με nodes & relationships.

 - Φόρτωση στο Neo4j με το loader script (nodes/relationships με βάρη και normalized appearances).

 - Καθαρισμός temporary workspace.

- Το project εκθέτει και REST API με FastAPI:

  - **GET /health**
    - Κάνω health check του server.

  - **POST /parse**
    - Τρέχει το pipeline για συγκεκριμένο GitHub repo
      - Παίρνει παραμέτρους :
        - choice [η γλώσσα προγραμματισμού του REPO]
        - repo_url

Για να τρέξει το api.py πρέπει :

- ```pip install libcst lxml fastapi pydantic uvicorn "neo4j==5.28.2" nltk```

- ```npm install @babel/parser @babel/traverse```

- να εχει εγκατασταθει το srcml διοτι αλλιως ΔΕΝ θα τρεξουν οι parsers (c, cpp, java) που το χρησιμοποιουν

- το αρχείο api.py να βρίσκεται στον ίδιο φάκελο με το .venv που θα δημιουργηθεί

---

**Pipeline εκτέλεσης**

- Σηκώνω server : ```uvicorn api:app```

- Στέλνω αίτημα GET /health με το Postman :
  - ```GET http://127.0.0.1:8000/health```

- Στέλνω αίτημα POST /parse με το Postman :
  - ```POST http://127.0.0.1:8000/parse```
      ```
      {
        "choice": "1",
        "repo_url": "https://github.com/robotics-4-all/intelligent_robot_systems"
      }
      ```


Εναλλακτικά, ανοίγω δεύτερο terminal στο Visual Studio Code :

- GET /health :

```curl http://127.0.0.1:8000/health```

- POST /parse :

```Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8000/parse' -ContentType 'application/json' -Body '{"choice":"1","repo_url":"https://github.com/robotics-4-all/intelligent_robot_systems"}'```
  
---

[pipeline_execution_photos](https://github.com/gpittis/Domain-Concepts-KG/tree/main/pipeline%20execution%20photos) : περιέχει πολλές photos που δείχνουν τα βήματα εκτέλεσης και τα αποτελέσματα 

---

[results_json](https://github.com/gpittis/Domain-Concepts-KG/tree/main/results_json) : Περιέχει όλα τα JSON αρχεία που παράγονται σε κάθε βήμα για κάθε parser

---

**BERTopic**

[bertopic_comments_analysis.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/BERTopic_comments_analysis/bertopic_comments_analysis.py)

Σπάζω τα comments που βρήκε ο parser σε documents. Κάθε γραμμή comments είναι 1 document. Έτσι, δημιουργώ ένα dataset από πολλά documents και το τροφοδοτώ στο bertopic. Το bertopic βρίσκει τα κυρίαρχα topics.

- Θα πρέπει να αλλάζω κατάλληλα τα hyperparameters του bertopic για να πετύχω βέλτιστη απόδοση σε κάθε codebase.
- Έκανα 2 δοκιμές με τα codebases : [intelligent_robot_systems](https://github.com/robotics-4-all/intelligent_robot_systems) και [streamsim](https://github.com/robotics-4-all/streamsim)
- Τα αποτελέσματα είναι οι εικόνες στο φάκελο [BERTopic_comments_analysis](https://github.com/gpittis/Domain-Concepts-KG/tree/main/BERTopic_comments_analysis)
