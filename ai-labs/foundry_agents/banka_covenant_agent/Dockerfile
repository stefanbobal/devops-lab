# Covenant agent for Azure AI Foundry hosted agents. Build for linux/amd64 (the platform requires x86_64).
FROM python:3.12-slim

ENV PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements-foundry.txt .
RUN pip install -r requirements-foundry.txt

# Only what the chain imports. Trusted documents (data/) are part of the image, never an upload.
COPY foundry_app.py agent.py config.py providers.py covenants.py sources.py contract_rules.py \
     rag_prompt.py search.py thresholds.py thresholds.json load_documents.py ./
COPY data ./data

# Profiles are fixed here; model names and secrets come from the agent version's environment.
ENV LLM_PROFILE=azure EMBED_PROFILE=azure

EXPOSE 8088
CMD ["python", "foundry_app.py"]
