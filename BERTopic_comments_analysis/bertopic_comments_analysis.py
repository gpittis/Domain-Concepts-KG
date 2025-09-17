import json
import re
from pathlib import Path

json_filename = "comments_only_cpp_lang.json"   # δώσε εδώ το όνομα του JSON
output_dir = Path("dataset_comments")           # φάκελος για αποθήκευση .txt (αυτός ο φάκελος είναι το dataset που θα δεχθεί το bertopic)

# καθαρίζω ειδικούς χαρακτήρες
ESCAPES_PATTERN = re.compile(r"[\n\t\r\f\v]")
LEADING_STARS_PATTERN = re.compile(r"^\s*\*+\s?")
LINE_COMMENT_PREFIXES = [
    re.compile(r"^\s*//+"),         # C/C++/Java/JS
    re.compile(r"^\s*#(?!!)")       # Python
]
BLOCK_COMMENT_TOKENS = [
    re.compile(r"/\*+"),            # /*, /**, /*! ...
    re.compile(r"\*+/")             # */
]
TRIPLE_QUOTES_TOKENS = [
    re.compile(r"^\s*['\"]{3}"),    # """ ή ''' αρχή
    re.compile(r"['\"]{3}\s*$")     # """ ή ''' τέλος
]
DOXYGEN_JAVADOC_TAGS = re.compile(r"@\w+")
MULTISPACE_PATTERN = re.compile(r"\s+")

def clean_comment(text: str) -> str:
    """Καθαρίζει σχόλια για C/C++/Python/Java/JS"""
    if not text:
        return ""

    text = ESCAPES_PATTERN.sub(" ", text)
    for pat in LINE_COMMENT_PREFIXES:
        text = pat.sub(" ", text)
    for pat in BLOCK_COMMENT_TOKENS:
        text = pat.sub(" ", text)
    for pat in TRIPLE_QUOTES_TOKENS:
        text = pat.sub(" ", text)
    text = LEADING_STARS_PATTERN.sub(" ", text)
    text = DOXYGEN_JAVADOC_TAGS.sub(" ", text)
    text = MULTISPACE_PATTERN.sub(" ", text).strip()
    return text


# =========================
# ΦΟΡΤΩΣΗ JSON + ΚΑΘΑΡΙΣΜΟΣ
# =========================
with open(json_filename, "r", encoding="utf-8") as f:
    data = json.load(f)

all_comments = []
for entry in data:
    for comment in entry.get("comments", []):
        for line in comment.split("\n"):   # σπάμε block σχόλια σε γραμμές
            cleaned = clean_comment(line.strip())
            if cleaned:
                all_comments.append(cleaned)

print(f"Συνολικά {len(all_comments)} σχόλια βρέθηκαν και καθαρίστηκαν.")

# =========================
# ΑΠΟΘΗΚΕΥΣΗ ΣΕ .TXT
# =========================
output_dir.mkdir(exist_ok=True)  # δημιουργεί τον φάκελο αν δεν υπάρχει

for i, comment in enumerate(all_comments, 1):
    file_path = output_dir / f"doc_{i}.txt"
    file_path.write_text(comment, encoding="utf-8")

print(f"Αποθηκεύτηκαν {len(all_comments)} αρχεία στο φάκελο {output_dir.resolve()}")

# =========================
# ΕΤΟΙΜΟ ΓΙΑ BERTopic
# =========================
docs = all_comments

# =========================
# BERTopic PIPELINE
# =========================
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
from umap import UMAP
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer
from bertopic.representation import KeyBERTInspired
from bertopic.vectorizers import ClassTfidfTransformer

# Embeddings
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
embeddings = embedding_model.encode(docs, show_progress_bar=True)

# UMAP (dimension reduction)
umap_model = UMAP(
    n_neighbors=50,
    n_components=50,
    min_dist=0.0,
    metric='cosine',
    random_state=42
)

# HDBSCAN (clustering)
hdbscan_model = HDBSCAN(
    min_cluster_size=100,
    metric='euclidean',
    cluster_selection_method='eom',
    prediction_data=True
)

# Vectorizer
vectorizer_model = CountVectorizer(
    stop_words="english",
    min_df=1,
    ngram_range=(1, 2)
)

# Representation
keybert_model = KeyBERTInspired()
ctfidf_model = ClassTfidfTransformer(reduce_frequent_words=True)

# BERTopic
topic_model = BERTopic(
    embedding_model=embedding_model,
    umap_model=umap_model,
    hdbscan_model=hdbscan_model,
    vectorizer_model=vectorizer_model,
    ctfidf_model=ctfidf_model,
    representation_model=keybert_model,
    top_n_words=10,
    verbose=True
)

# Fit
topics, probs = topic_model.fit_transform(docs, embeddings)

# Προβολή βασικών πληροφοριών
info = topic_model.get_topic_info()
print(info)

# Εκτύπωση των topic representations
r = info["Representation"]
for i in range(len(r) - 1):
    print("Topic " + str(i) + " : \n" + " | ".join(r[i + 1]))
    print("------------------")