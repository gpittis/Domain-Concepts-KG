import json, re
from typing import Any
from pathlib import Path

# --------------------- STOPWORDS (from JSONs) ----------------------

# List of JSON files that each contain a flat list of strings (stopwords / common code words).
# The final STOPWORDS set is the union of all words from the files that actually exist on disk.
# sources : 
# - nltk (python library)
# - nltk.corpus
# - https://github.com/e3b0c442/keywords
# - https://github.com/stopwords-iso/stopwords-iso
# - https://github.com/abbrcode/abbreviations-in-code
# - chat gpt 
STOPWORD_FILES = [
    Path("common_code_words_manually_collected.json"),
    Path("stopwords_list_from_stopwords_iso_github_repo.json"),
    Path("nltk_english_stopwords.json"),
    Path("common_verbs_list.json")
]

def _load_word_list_json(path: Path) -> list[str]:
    """
    Load a JSON file that is expected to be a list of strings.
    Returns the list lowercased and stripped, filtering out empty strings.
    This function assumes the JSON is a simple array like ["word1", "word2", ...].
    """
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # Normalize: keep only non-empty strings, strip whitespace, lowercase for consistent matching.
    return [x.strip().lower() for x in data if x.strip()]

# Build the final STOPWORDS set by aggregating (union) words from all present files.
STOPWORDS: set[str] = set()
for p in STOPWORD_FILES:
    if p.exists():
        STOPWORDS.update(_load_word_list_json(p))


# --------------------- TOKEN SPLIT / CLEANING -----------------------------

# Regex to split CamelCase / PascalCase and acronyms boundaries.
# Explanation:
# - (?<=[A-Z])(?=[A-Z][a-z]) : Split between an uppercase letter and another uppercase letter
#   that is followed by a lowercase letter (e.g., "HTTPServer" -> "HTTP|Server").
# - (?<=[a-z])(?=[A-Z])     : Split between a lowercase letter and an uppercase letter
#   (e.g., "createdAt" -> "created|At").
CAMEL_RE = re.compile(
    r'(?<=[A-Z])(?=[A-Z][a-z])'  # boundary: end of acronym block before a normal word
    r'|(?<=[a-z])(?=[A-Z])'      # boundary: camelCase transition (lower -> Upper)
)

def split_token(token: str) -> list[str]:
    """
    Break a single token into sub-words using:
      - CamelCase / PascalCase splitting (including acronym-to-word boundaries)
      - Underscore / dash / dot delimiters
    Returns a list of split chunks without further normalization (no lowercasing here).
    """
    # First split by common structural delimiters: underscore, dash, dot.
    # Example: "foo_bar-baz.qux" -> ["foo", "bar", "baz", "qux"]
    parts = re.split(r"[_\-.]+", token)
    final: list[str] = []
    for p in parts:
        # For each part, insert spaces at camel/acronym boundaries via CAMEL_RE,
        # then split by whitespace to produce individual sub-tokens.
        final.extend(re.sub(CAMEL_RE, " ", p).split())
    return final

# --- letter<->digit boundary split ---
def split_letter_digit_boundaries(text: str) -> str:
    """
    Insert spaces between letter and digit boundaries (both directions).
    Examples:
      "var1" -> "var 1"
      "variable1Pele" -> "variable 1 Pele"
    """
    return re.sub(r'(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])', ' ', text)


def _filter_once(s: str) -> str:
    """
    Perform one pass of normalization + tokenization + filtering:
    First we normalize and tokenize the string until all tokens are fully split and cannot be broken further. 
    After that, we apply all filters once.

      Tokenization : 
      - Split letters/digits boundaries (adds spaces).
      - Replace any non-word char with space.
      - Split tokens on whitespace; for each token, further split on camel/acronym boundaries.
      - Normalize tokens (lowercase, strip underscores/dashes at ends).

      Filtering:
      - tokens with length < 3
      - purely numeric tokens
      - hex-like tokens matching '0x[0-9a-f]+'
      - tokens present in STOPWORDS

      Join the kept tokens back with single spaces.
    """

    # split letter<->digit boundaries to surface additional splits later
    s = split_letter_digit_boundaries(s)

    # normalize non-word characters to spaces
    # This removes punctuation etc., leaving letters, digits, and underscore as word chars.
    s = re.sub(r"[^\w]", " ", s)

    # coarse tokenization on whitespace, then fine splitting for camel/acronym
    tokens: list[str] = []
    for raw in s.split():
        tokens.extend(split_token(raw))

    # lowercase and trim leading/trailing underscores/dashes that may remain
    tokens = [t.lower().strip("_-") for t in tokens if t]

    # filtering rules (strict)
    kept: list[str] = []
    for t in tokens:
        # Drop very short tokens (< 3 chars).
        if len(t) < 3:
            continue
        # Drop pure numbers (e.g., "2024").
        if t.isdigit():
            continue
        # Drop hex-like values with a lowercase '0x' prefix
        if re.fullmatch(r"0x[0-9a-f]+", t):  # hex-like
            continue
        # Drop anything that is in the STOPWORDS set.
        if t in STOPWORDS:
            continue
        kept.append(t)

    # remove consecutive duplicates
    deduped: list[str] = []
    for t in kept:
        if not deduped or deduped[-1] != t:
            deduped.append(t)

    # return a space-joined string of the kept tokens
    return " ".join(deduped)

# --- Recursive traversal for dict/list/str containers ---
def recurse(x: Any) -> Any:
    """
    Recursively traverse a JSON-like structure (dict/list/str/other):
      - dict: apply recursively to values (keys remain unchanged).
      - list: apply recursively to each element.
      - str : apply _filter_once (tokenization + cleaning).
      - other types: return as-is.
    Returns a structure of the same shape with strings cleaned.
    """
    if isinstance(x, dict):
        return {k: recurse(v) for k, v in x.items()}
    elif isinstance(x, list):
        return [recurse(v) for v in x]
    elif isinstance(x, str):
        return _filter_once(x)
    else:
        return x

def run_concept_filter(input_json: str, output_json: str | None = None) -> Path:
    """
    Παίρνει το JSON του parser, περνάει από recurse(...), και γράφει
    νέο JSON με ίδιο ακριβώς schema (απλώς φιλτραρισμένο).
    Αν δεν δοθεί output_json, φτιάχνει αυτόματα όνομα με suffix.
    Επιστρέφει το τελικό Path.
    """
    in_path = Path(input_json).resolve()
    if output_json is None:
        output_json = str(in_path.with_name(in_path.stem + "_cleaned_from_non_concepts.json"))
    out_path = Path(output_json).resolve()

    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cleaned = recurse(data)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    # print(f"[ok] {in_path} -> {out_path}")
    return out_path


