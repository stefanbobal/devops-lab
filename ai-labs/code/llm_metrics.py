"""Non-streaming LLM calls with provider-reported usage; no text/token heuristics."""
import math
import time
from datetime import date


def validate_prices(prices):
    if prices.get("currency") != "USD" or not isinstance(prices.get("models"), dict):
        raise ValueError("Prices require currency USD and a models object")
    for model, rate in prices["models"].items():
        if not isinstance(rate, dict) or ":" not in model:
            raise ValueError("Price keys must be provider:model, with a rate object")
        start = date.fromisoformat(rate["effective_from"])
        if rate.get("estimate_from") and date.fromisoformat(rate["estimate_from"]) > start:
            raise ValueError("estimate_from must not follow effective_from")
        if rate.get("effective_to") and date.fromisoformat(rate["effective_to"]) < start:
            raise ValueError("Price effective_to precedes effective_from")
        tiers = rate.get("tiers", [rate])
        if not isinstance(tiers, list) or not tiers:
            raise ValueError("Pricing tiers must be a nonempty list")
        previous = 0
        for i, tier in enumerate(tiers):
            for key in ("input_per_million", "output_per_million"):
                if key not in tier:
                    raise ValueError(model + " missing " + key)
            for key, value in tier.items():
                if key.endswith("_per_million") and (isinstance(value, bool) or
                    not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
                    raise ValueError(model + " invalid rate " + key)
            bound = tier.get("max_input_tokens")
            if bound is None:
                if i != len(tiers) - 1:
                    raise ValueError("Only the final pricing tier may be unbounded")
            elif isinstance(bound, bool) or not isinstance(bound, int) or bound <= previous:
                raise ValueError("Pricing tier limits must be increasing positive integers")
            else:
                previous = bound


def plain(value):
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return dict(value)


def normalize_usage(provider, raw):
    """Output includes reasoning where billed; never add Azure reasoning twice."""
    cached = created = reasoning = 0
    if provider == "azure":
        incoming, outgoing = raw.get("prompt_tokens"), raw.get("completion_tokens")
        cached = (raw.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        reasoning = (raw.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0
    elif provider == "anthropic":
        cached = raw.get("cache_read_input_tokens", 0) or 0
        created = raw.get("cache_creation_input_tokens", 0) or 0
        incoming = raw.get("input_tokens")
        incoming = incoming + cached + created if incoming is not None else None
        outgoing = raw.get("output_tokens")
        reasoning = None  # not separately reported by this API
    elif provider == "vertex":
        incoming = raw.get("prompt_token_count")
        cached = raw.get("cached_content_token_count", 0) or 0
        reasoning = raw.get("thoughts_token_count", 0) or 0
        visible = raw.get("candidates_token_count")
        outgoing = visible + reasoning if visible is not None else None
    elif provider == "ollama":
        incoming, outgoing = raw.get("prompt_eval_count"), raw.get("eval_count")
        cached = raw.get("prompt_eval_cached_count", 0) or 0
        reasoning = None
    else:
        raise ValueError(provider)
    return dict(input_tokens=incoming, output_tokens=outgoing,
                cached_input_tokens=cached, cache_creation_tokens=created,
                reasoning_tokens=reasoning)


def estimate_cost(provider, model, usage, prices, pricing_date):
    """USD estimate only. Exact model keys, date bounds, no fabricated cloud prices."""
    if provider == "ollama":
        return {"estimated_cost_usd": 0.0, "cost_status": "local_api_fee_only"}
    rate = prices.get("models", {}).get(provider + ":" + model)
    def unknown(reason):
        return {"estimated_cost_usd": None, "cost_status": reason}
    if not rate:
        return unknown("missing_price")
    day = date.fromisoformat(pricing_date)
    future_rate = day < date.fromisoformat(rate["effective_from"])
    earliest = date.fromisoformat(rate.get("estimate_from", rate["effective_from"]))
    if day < earliest or (
        rate.get("effective_to") and day > date.fromisoformat(rate["effective_to"])
    ):
        return unknown("price_outside_effective_dates")
    incoming, outgoing = usage["input_tokens"], usage["output_tokens"]
    if incoming is None or outgoing is None:
        return unknown("missing_usage")
    if rate.get("tiers"):
        tiers = rate["tiers"]
        selected = next((tier for tier in tiers if tier.get("max_input_tokens") is None
                         or incoming <= tier["max_input_tokens"]), None)
        if selected is None:
            return unknown("pricing_tier_exceeded")
        rate = {**rate, **selected}
    if rate.get("max_input_tokens") and incoming > rate["max_input_tokens"]:
        return unknown("pricing_tier_exceeded")
    cached, created = usage["cached_input_tokens"], usage["cache_creation_tokens"]
    uncached = incoming - cached - created
    if min(uncached, outgoing, cached, created) < 0:
        return unknown("invalid_usage")
    total = 0.0
    for count, key in ((uncached, "input_per_million"), (outgoing, "output_per_million"),
                       (cached, "cached_input_per_million"), (created, "cache_creation_per_million")):
        if not count:
            continue
        value = rate.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            return unknown("missing_or_invalid_" + key)
        total += count * value / 1_000_000
    return {"estimated_cost_usd": total, "cost_status": "estimated_future_rate" if future_rate else "estimated",
            "price_source": rate.get("source")}


def chat_measured(system, user, max_tokens=4096, timeout=180, ollama_num_ctx=8192):
    from config import LLM_MODEL, LLM_PROVIDER, GCP_PROJECT, VERTEX_LLM_LOCATION
    provider, model = LLM_PROVIDER, LLM_MODEL
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    started = time.perf_counter()
    extra = {}
    if provider == "azure":
        from providers import _get_azure_client
        response = _get_azure_client().with_options(max_retries=0, timeout=timeout).chat.completions.create(
            model=model, messages=messages, max_completion_tokens=max_tokens)
        raw = plain(response.usage)
        choice = response.choices[0] if response.choices else None
        answer = choice.message.content if choice else ""
        finish = choice.finish_reason if choice else "no_choices"
        resolved = response.model
        extra["request_id"] = getattr(response, "_request_id", None)
        complete = finish == "stop"
    elif provider == "anthropic":
        import anthropic
        with anthropic.Anthropic(max_retries=0, timeout=timeout) as client:
            response = client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                              messages=[messages[1]])
        raw = plain(response.usage)
        answer = "".join(b.text for b in response.content if b.type == "text")
        finish, resolved = response.stop_reason, response.model
        extra["request_id"] = getattr(response, "_request_id", None)
        complete = finish == "end_turn"
    elif provider == "vertex":
        from google import genai
        from google.genai import types
        with genai.Client(vertexai=True, project=GCP_PROJECT, location=VERTEX_LLM_LOCATION,
                          http_options=types.HttpOptions(timeout=int(timeout * 1000),
                              retry_options=types.HttpRetryOptions(attempts=1))) as client:
            response = client.models.generate_content(model=model, contents=user,
                config=types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens))
        raw = plain(response.usage_metadata)
        answer = response.text or ""
        candidate = response.candidates[0] if response.candidates else None
        finish = str(getattr(candidate, "finish_reason", "no_candidates")).split(".")[-1]
        resolved = getattr(response, "model_version", None)
        extra["request_id"] = getattr(response, "response_id", None)
        complete = finish == "STOP"
    elif provider == "ollama":
        import ollama
        if ollama_num_ctx <= max_tokens:
            raise ValueError("Ollama context must exceed output cap to leave room for the prompt")
        response = ollama.Client(timeout=timeout).chat(model=model, messages=messages, stream=False,
            options={"num_predict": max_tokens, "num_ctx": ollama_num_ctx})
        extra["ollama_num_ctx"] = ollama_num_ctx
        data = plain(response)
        raw = {k: v for k, v in data.items() if k.endswith("_count") or k.endswith("_duration")}
        answer = (data.get("message") or {}).get("content", "")
        finish, resolved = data.get("done_reason"), data.get("model")
        complete = data.get("done") is True and finish == "stop"
        for field in ("load_duration", "prompt_eval_duration", "eval_duration", "total_duration"):
            extra[field + "_s"] = raw[field] / 1e9 if raw.get(field) is not None else None
        seconds = extra["eval_duration_s"]
        extra["generation_tokens_per_second"] = raw.get("eval_count", 0) / seconds if seconds else None
    else:
        raise ValueError("Unsupported provider: " + provider)
    elapsed = time.perf_counter() - started
    usage = normalize_usage(provider, raw)
    return dict(provider=provider, model=model, resolved_model=resolved, answer=answer,
                status="ok" if complete and answer and answer.strip() else "incomplete",
                finish_reason=finish, llm_latency_s=elapsed, usage_raw=raw, **usage, **extra,
                output_tokens_per_wall_second=(usage["output_tokens"] / elapsed
                    if usage["output_tokens"] is not None and elapsed > 0 else None))
