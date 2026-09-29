# AI Lab 02 – Embeddings

## Goal

Understand how text becomes a vector and how "similar meaning" is measured.

## Concepts

- **Embedding:** a list of numbers (here 768) that represents the meaning of a text.
- **Cosine similarity:** how close two vectors point in the same direction.
  1 = same meaning, close to 0 = unrelated.
- Sentences with similar meaning get similar vectors even if they share almost no words.

## Steps

```bash
cd ~/devops-lab/ai-labs/code
source venv/bin/activate
python embeddings_test.py
```

## What to observe

- "slow" vs. "high response times" should score higher than "slow" vs. "backup failed".
- The coffee machine should be far from everything.
- The Slovak sentence is probably weakly linked to the English ones: `nomic-embed-text`
  is trained mainly on English. Language support matters when choosing a model for production.
- Scores do not use the full 0–1 range, typically 0.4–0.9. A similarity threshold must be
  tuned by experiment.

## Experiment

Add your own sentences (no company data) and see what the model considers similar.

## Notes


sapops@k8s-lab:~/devops-lab/ai-labs/code$ python embeddings_test.py
Vector dimension: 768
0.64  SAP system is very slow for users  <->  High dialog response times on application server
0.42  SAP system is very slow for users  <->  HANA data backup failed
0.43  SAP system is very slow for users  <->  Backint returned SSL handshake error during backup
0.36  SAP system is very slow for users  <->  Coffee machine on the third floor is broken
0.65  SAP system is very slow for users  <->  SAP systém je veľmi pomalý
0.36  High dialog response times on application server  <->  HANA data backup failed
0.42  High dialog response times on application server  <->  Backint returned SSL handshake error during backup
0.36  High dialog response times on application server  <->  Coffee machine on the third floor is broken
0.46  High dialog response times on application server  <->  SAP systém je veľmi pomalý
0.58  HANA data backup failed  <->  Backint returned SSL handshake error during backup
0.36  HANA data backup failed  <->  Coffee machine on the third floor is broken
0.43  HANA data backup failed  <->  SAP systém je veľmi pomalý
0.34  Backint returned SSL handshake error during backup  <->  Coffee machine on the third floor is broken
0.45  Backint returned SSL handshake error during backup  <->  SAP systém je veľmi pomalý
0.37  Coffee machine on the third floor is broken  <->  SAP systém je veľmi pomalý
sapops@k8s-lab:~/devops-lab/ai-labs/code$ 


-
