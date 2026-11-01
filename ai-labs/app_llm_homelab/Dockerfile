FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home appuser
COPY index.html styles.css app.mjs data.mjs schema.sql db_store.py db_import.py api_server.py ./
USER appuser
EXPOSE 8008
CMD ["python", "api_server.py", "--host", "0.0.0.0", "--port", "8008"]
