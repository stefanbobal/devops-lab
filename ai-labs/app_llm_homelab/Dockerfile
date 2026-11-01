FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY app_llm_homelab/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home appuser
COPY app_llm_homelab/index.html app_llm_homelab/styles.css app_llm_homelab/app.mjs app_llm_homelab/data.mjs app_llm_homelab/judge_ui.mjs ./
COPY app_llm_homelab/schema.sql app_llm_homelab/db_store.py app_llm_homelab/db_import.py app_llm_homelab/api_server.py ./
COPY app_llm_homelab/judge_core.py app_llm_homelab/judge_worker.py app_llm_homelab/judge_control.py app_llm_homelab/judge_providers.py ./
COPY app_llm_homelab/judge_schema.sql app_llm_homelab/judge_rubrics.json app_llm_homelab/judge_references.json ./
COPY code/llm_metrics.py ./bench_metrics.py
COPY code/llm_prices.json ./judge_prices.json
USER appuser
EXPOSE 8008
CMD ["python", "api_server.py", "--host", "0.0.0.0", "--port", "8008"]
