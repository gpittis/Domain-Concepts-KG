# Domain-Concepts-KG
Domain Concepts Knowledge Graph created by static analysis


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

Τα 3 παρακάτω αρχεία ΔΕΝ τα χρησιμοποίησα στο api :

[cleaning_from_top_level_structs_the_nested_attributes_C_lang.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/cleaning_from_top_level_structs_the_nested_attributes_C_lang.py)

[cleaning_the_top_level_classes_from_nested_elements_CPP.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/cleaning_the_top_level_classes_from_nested_elements_CPP.py)

[cleaning_nested_attributes_JAVA.py](https://github.com/gpittis/Domain-Concepts-KG/blob/main/cleaning_nested_attributes_JAVA.py)

Οι parsers που στηρίζονται στο srcML παρουσιάζουν το εξής πρόβλημα :

Όταν υπάρχουν nested classes , τότε τα attributes και τα methods των nested κλάσεων αποδίδονται και στη "parent" class που περιέχει τις nested classes. Έτσι, η parent class περιέχει επιπλέον και τα attributes και τα methods των child classes. Οπότε, με τα 3 αυτά scripts , επεξεργάζομαι το json που παράγει ο parser και αφαιρώ τα περιττά attributes και methods από τις parent classes. Η λογική που ακολουθούν αυτα τα 3 scripts είναι η εξής : 

Αν όλα τα attributes και όλα τα methods που περιέχει μια κλάση Α, εμφανίζονται ταυτόχρονα και σε μια άλλη κλάση Β και αυτή η κλάση Β περιέχει και επιπλέον attributes και επιπλέον methods , τότε η B είναι η parent class και η Α είναι η child class. Οπότε, αφαιρώ από τη κλάση Β , όλα εκείνα τα attributes και όλα εκείνα τα methods που υπάρχουν και στη κλάση Α. 

Ωστόσο, αυτη η πρακτική ΔΕΝ ΕΙΝΑΙ ΠΑΝΤΑ σωστή. Αυτό γιατί αν οι 2 κλάσεις περιέχουν όντως κοινα attributes και κοινά methods , τότε μπορεί να γίνει λανθασμένη διαγραφή και να χάσω πληροφορία. 

Από την άλλη, θεωρώ πως δεν είναι λάθος να εμφανίζονται στην parent class και τα attributes/methods των childs, διότι με αυτό τον τρόπο στον Knowledge Graph οι parent και childs classes θα μοιράζονται πολλά κοινά nodes και έτσι θα φαίνεται ότι υπάρχει κάποια σύνδεση μεταξύ τους. 

Θα ήθελα να μου πείτε την γνώμη σας για αυτό το κομμάτι.

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

- Επαναληπτικό καθάρισμα

  - Εφαρμόζει όλα τα παραπάνω φίλτρα επανειλημμένα μέχρι το αποτέλεσμα να σταθεροποιηθεί ή να φτάσει max 5 επαναλήψεις (safety cap). Αυτό το κάνω διότι μετά από την εφαρμογή οποιουδήποτε φίλτρου, μπορεί να εμφανιστούν νέα tokens τα οποία μπορούν να αφαιρεθούν ή να καθαριστούν περαιτέρω.

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

  --- 
- **ΚΑΝΟΝΕΣ querying με τα final_weights των relationships**

Σηκώνω server :
uvicorn api:app    

Server Health :
curl http://127.0.0.1:8000/health

Στέλνω post request για να κανω parse github codebase :
Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8000/parse' -ContentType 'application/json' -Body '{"choice":"1","repo_url":"https://github.com/robotics-4-all/intelligent_robot_systems"}'

Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8000/parse' -ContentType 'application/json' -Body '{"choice":"3","repo_url":"https://github.com/robotics-4-all/streamsim"}'

Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8000/parse' -ContentType 'application/json' -Body '{"choice":"2","repo_url":"https://github.com/clibs/clib/tree/master"}'

Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8000/parse' -ContentType 'application/json' -Body '{"choice":"4","repo_url":"https://github.com/PhilJay/MPAndroidChart"}'

Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8000/parse' -ContentType 'application/json' -Body '{"choice":"4","repo_url":"https://github.com/iluwatar/java-design-patterns"}'

Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:8000/parse' -ContentType 'application/json' -Body '{"choice":"5","repo_url":"https://github.com/veertly/app"}'


pip install libcst lxml fastapi pydantic uvicorn neo4j

npm install @babel/parser @babel/traverse

uvicorn api:app



MATCH (n)
OPTIONAL MATCH (n)-[r]-(m)
RETURN DISTINCT n, r, m


MATCH (a)-[r]->(b)
WHERE r.final_weight >= 0.7
  AND NOT a.name =~ "^(FILE|CLASS|REPO|FUNCTION|METHOD|NESTED_CLASS|NESTED_FUNCTION)_ANON_.*"
  AND NOT b.name =~ "^(FILE|CLASS|REPO|FUNCTION|METHOD|NESTED_CLASS|NESTED_FUNCTION)_ANON_.*"
  AND (
      toLower(a.name) CONTAINS "robot" 
      OR toLower(b.name) CONTAINS "robot"
  )
RETURN a, r, b


εννοειται να εχει εγκατασταθει το srcml διοτι αλλιως ΔΕΝ θα τρεξουν οι parsers (c, cpp, java) που το χρησιμοποιουν
