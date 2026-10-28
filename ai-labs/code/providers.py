"""One place that talks to the models: local Ollama or a cloud API.

embed(text, kind) -> vector     kind = "document" (stored incidents), "query" (a new incident)
                                or "similarity" (comparing sentences, Lab 02)
chat(system, user) -> text      the LLM answer
"""
import os

import numpy as np

from config import (EMBED_DIM, EMBED_MODEL, EMBED_PROVIDER, GCP_PROJECT, LLM_MODEL,
                    LLM_PROVIDER, PROFILE, VERTEX_EMBED_LOCATION, VERTEX_LLM_LOCATION)

_azure_client = None


def _get_azure_client():
    global _azure_client
    if _azure_client is None:
        from openai import OpenAI

        _azure_client = OpenAI(
            base_url=os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1/",
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
        )
    return _azure_client


def embed(text, kind="document"):
    if PROFILE == "nomic_prefix":
        if kind == "document":
            text = "search_document: " + text
        elif kind == "query":
            text = "search_query: " + text

    if EMBED_PROVIDER == "ollama":
        import ollama
        if PROFILE == "qwen_instr" and kind == "query":
            text = ("Instruct: Given an incident description, retrieve the most relevant "
                    f"historical incidents\nQuery:{text}")
        vector = ollama.embed(model=EMBED_MODEL, input=text)["embeddings"][0]

    elif EMBED_PROVIDER == "vertex":
        from google import genai
        from google.genai import types
        client = genai.Client(vertexai=True, project=GCP_PROJECT, location=VERTEX_EMBED_LOCATION)
        task = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY",
                "similarity": "SEMANTIC_SIMILARITY"}[kind]
        result = client.models.embed_content(
            model=EMBED_MODEL,
            contents=text,
            config=types.EmbedContentConfig(task_type=task, output_dimensionality=EMBED_DIM),
        )
        vector = result.embeddings[0].values

    elif EMBED_PROVIDER == "azure":
        result = _get_azure_client().embeddings.create(
            model=os.environ["AZURE_OPENAI_EMBED_DEPLOYMENT"], input=text
        )
        vector = result.data[0].embedding

    else:
        raise SystemExit(f"Unknown embedding provider: {EMBED_PROVIDER}")

    if len(vector) != EMBED_DIM:
        raise SystemExit(f"{EMBED_MODEL} returned {len(vector)} dims, config expects {EMBED_DIM}")
    return np.array(vector)


def chat(system_prompt, user_prompt):
    if LLM_PROVIDER == "ollama":
        import ollama
        response = ollama.chat(model=LLM_MODEL, messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        return response["message"]["content"]

    if LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from the environment / .env
        response = client.messages.create(
            model=LLM_MODEL, max_tokens=2000, system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    if LLM_PROVIDER == "vertex":
        from google import genai
        from google.genai import types
        client = genai.Client(vertexai=True, project=GCP_PROJECT, location=VERTEX_LLM_LOCATION)
        response = client.models.generate_content(
            model=LLM_MODEL, contents=user_prompt,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        return response.text

    raise SystemExit(f"Unknown LLM provider: {LLM_PROVIDER}")