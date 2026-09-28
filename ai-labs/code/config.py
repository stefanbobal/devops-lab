"""Shared settings for all AI labs. Override any value with an environment variable."""
import os

PG_DSN = os.getenv("PG_DSN", "host=localhost user=postgres password=lab dbname=postgres")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
LLM_MODEL = os.getenv("LLM_MODEL", "gemma3:27b")
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.60"))
