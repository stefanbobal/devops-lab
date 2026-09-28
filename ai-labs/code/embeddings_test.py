"""Lab 02: compare the meaning of sentences using embeddings."""
import numpy as np
import ollama

from config import EMBED_MODEL

sentences = [
    "SAP system is very slow for users",
    "High dialog response times on application server",
    "HANA data backup failed",
    "Backint returned SSL handshake error during backup",
    "Coffee machine on the third floor is broken",
    "SAP systém je veľmi pomalý",
]

response = ollama.embed(model=EMBED_MODEL, input=sentences)
vectors = np.array(response["embeddings"])
print("Vector dimension:", vectors.shape[1])

# cosine similarity: 1 = same meaning, close to 0 = unrelated
vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
similarity = vectors @ vectors.T

for i in range(len(sentences)):
    for j in range(i + 1, len(sentences)):
        print(f"{similarity[i, j]:.2f}  {sentences[i]}  <->  {sentences[j]}")
