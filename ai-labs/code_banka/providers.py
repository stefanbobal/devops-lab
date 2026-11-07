"""One place that talks to the models: local Ollama or a cloud API.

embed(text, kind) -> vector     kind = "document" (stored contract articles), "query" (a search question)
                                or "similarity" (comparing sentences, Lab 02)
chat(system, user) -> text      the LLM answer
"""
import os

import numpy as np

from config import (EMBED_DIM, EMBED_MODEL, EMBED_PROVIDER, GCP_PROJECT, LLM_MODEL,
                    LLM_PROVIDER, VERTEX_EMBED_LOCATION, VERTEX_LLM_LOCATION)

_azure_client = None


def _get_azure_client():
    global _azure_client
    if _azure_client is None:
        from openai import OpenAI

        _azure_client = OpenAI(
            base_url=(os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
                      if os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/").endswith("/openai/v1")
                      else os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1") + "/",
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
        )
    return _azure_client


def embed(text, kind="document"):
    if EMBED_PROVIDER == "ollama":
        import ollama
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


def _usage_dict(value):
    """Provider usage object -> plain dict (llm_metrics.normalize_usage turns it into token counts)."""
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return dict(value)


def chat_with_usage(system_prompt, user_prompt):
    """Same request as always, but returns (text, info). info: provider, model, latency_s, finish_reason and
    usage_raw as reported by the provider (no token estimates). Request parameters must stay identical to
    what T3/T5 used, so measuring does not change the model's behaviour."""
    import time
    started = time.perf_counter()
    raw, finish = {}, None

    if LLM_PROVIDER == "azure":
        if not LLM_MODEL:
            raise SystemExit("Set AZURE_OPENAI_LLM_DEPLOYMENT to your Azure chat deployment name.")
        for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"):
            if not os.getenv(name, "").strip():
                raise SystemExit(f"Set {name} before using Azure OpenAI.")
        response = _get_azure_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        if not response.choices:
            raise RuntimeError("Azure returned no completion choices.")
        choice = response.choices[0]
        if choice.finish_reason != "stop" or not choice.message.content:
            raise RuntimeError(
                f"Azure did not return a complete text answer (finish_reason={choice.finish_reason})."
            )
        text, finish, raw = choice.message.content, choice.finish_reason, _usage_dict(response.usage)

    elif LLM_PROVIDER == "ollama":
        import ollama
        response = ollama.chat(model=LLM_MODEL, messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        text = response["message"]["content"]
        data = _usage_dict(response)
        finish = data.get("done_reason")
        raw = {k: v for k, v in data.items() if k.endswith("_count") or k.endswith("_duration")}

    elif LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from the environment / .env
        response = client.messages.create(
            model=LLM_MODEL, max_tokens=2000, system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        finish, raw = response.stop_reason, _usage_dict(response.usage)

    elif LLM_PROVIDER == "vertex":
        from google import genai
        from google.genai import types
        client = genai.Client(vertexai=True, project=GCP_PROJECT, location=VERTEX_LLM_LOCATION)
        response = client.models.generate_content(
            model=LLM_MODEL, contents=user_prompt,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        text = response.text
        candidate = response.candidates[0] if response.candidates else None
        finish = str(getattr(candidate, "finish_reason", None)).split(".")[-1]
        raw = _usage_dict(response.usage_metadata)

    else:
        text = None

    info = dict(provider=LLM_PROVIDER, model=LLM_MODEL, latency_s=round(time.perf_counter() - started, 3),
                finish_reason=finish, usage_raw=raw)
    return text, info


def chat(system_prompt, user_prompt):
    return chat_with_usage(system_prompt, user_prompt)[0]
