"""Shared settings for all AI labs. Override any value with an environment variable or .env."""
import os

from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY etc. from .env in the current folder

# ---------- embedding models ----------
# provider: ollama (local GPU), vertex (Google Cloud), azure (Azure OpenAI)
MODELS = {
    "nomic":   {"provider": "ollama", "name": "nomic-embed-text",   "dim": 768},
    "nomic_prefix": {"provider": "ollama", "name": "nomic-embed-text", "dim": 768},
    "bge":     {"provider": "ollama", "name": "bge-m3",             "dim": 1024},
    "qwen":    {"provider": "ollama", "name": "qwen3-embedding:4b", "dim": 2560},
    "qwen_instr": {"provider": "ollama", "name": "qwen3-embedding:4b", "dim": 2560},
    "qwen8":   {"provider": "ollama", "name": "qwen3-embedding:8b", "dim": 4096},
    "gemini":  {"provider": "vertex", "name": os.getenv("VERTEX_EMBED_MODEL", "gemini-embedding-001"), "dim": 1536},
    "azure":   {"provider": "azure", "name": os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT", "text-embedding-3-small"), "dim": 1536},
}

PROFILE = os.getenv("EMBED_PROFILE", "nomic")
if PROFILE not in MODELS:
    raise SystemExit(f"Unknown EMBED_PROFILE '{PROFILE}', use one of: {', '.join(MODELS)}")

EMBED_PROVIDER = MODELS[PROFILE]["provider"]
EMBED_MODEL = MODELS[PROFILE]["name"]
EMBED_DIM = MODELS[PROFILE]["dim"]
TABLE = f"incident_memory_{PROFILE}"   # each embedding model has its own table

# ---------- LLMs for rag.py ----------
# provider: ollama (local GPU), anthropic (Claude API), vertex (Gemini on Google Cloud)
LLMS = {
    "azure":  {"provider": "azure", "name": os.getenv("AZURE_OPENAI_LLM_DEPLOYMENT", "").strip()},
    "gemma":  {"provider": "ollama",    "name": "gemma3:27b"},
    "qwen36": {"provider": "ollama",    "name": "qwen3.6:27b"},
    "qwen38": {"provider": "ollama",    "name": "qwen3.8:27b"},
    "llama":  {"provider": "ollama",    "name": "llama3.1:8b"},
    "claude": {"provider": "anthropic", "name": os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")},
    "haiku":  {"provider": "anthropic", "name": "claude-haiku-5-5"},
    "opus":   {"provider": "anthropic", "name": "claude-opus-5-5"},
    "gemini": {"provider": "vertex",    "name": os.getenv("VERTEX_LLM_MODEL", "gemini-3-flash-preview")},
    "gemini_argon": {"provider": "vertex", "name": os.getenv("VERTEX_ARGON_MODEL", "gemini-4-argon")},
}

LLM_PROFILE = os.getenv("LLM_PROFILE", "gemma")
if LLM_PROFILE not in LLMS:
    raise SystemExit(f"Unknown LLM_PROFILE '{LLM_PROFILE}', use one of: {', '.join(LLMS)}")

LLM_PROVIDER = LLMS[LLM_PROFILE]["provider"]
LLM_MODEL = LLMS[LLM_PROFILE]["name"]

# ---------- Google Cloud ----------
GCP_PROJECT = os.getenv("GCP_PROJECT", "ai-labs-512816")
VERTEX_EMBED_LOCATION = os.getenv("VERTEX_EMBED_LOCATION", "us-central1")
VERTEX_LLM_LOCATION = os.getenv("VERTEX_LLM_LOCATION", "global")

# ---------- database and search ----------
PG_DSN = os.getenv("PG_DSN", "host=localhost user=postgres password=heslo dbname=postgres")
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.60"))
