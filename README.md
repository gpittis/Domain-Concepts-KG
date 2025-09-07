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

- Weights σε nodes και relationships, ώστε να κωδικοποιούνται οι προτεραιότητες με DSL-oriented λογική και επιπλέον να γίνεται πιο εύκολο το querying.









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
