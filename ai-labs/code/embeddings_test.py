"""Lab 02: compare the meaning of sentences using embeddings (local or cloud model)."""
import numpy as np

from config import EMBED_MODEL, EMBED_PROVIDER
from providers import embed

sentences = [
    "Server with SAP system is now running high on CPU",
    "High dialog response times on application server",
    "Filesystem /oracle/SID/oraarch is full",
    "Backint returned SSL handshake error during backup",
    "Coffee machine on the third floor is broken",
    "HANA backint SSL verification failed",
    "ORA-01555 message in AlertSID.log"
]

vectors = np.array([embed(s, "similarity") for s in sentences])
print(f"Model: {EMBED_MODEL} ({EMBED_PROVIDER}) | vector dimension: {vectors.shape[1]}")

# cosine similarity: 1 = same meaning, unrelated sentences land around 0.3-0.4
vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
similarity = vectors @ vectors.T

for i in range(len(sentences)):
    for j in range(i + 1, len(sentences)):
        print(f"{similarity[i, j]:.2f}  {sentences[i]}  <->  {sentences[j]}")
