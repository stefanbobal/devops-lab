# Daily lab startup

On the Ubuntu VM, use this entry point whenever you start the lab:

```bash
cd ~/devops-lab/ai-labs/code
bash lab.sh
```

The launcher activates this directory's .venv, loads its .env, checks Docker,
connects to the database configured by PG_DSN, verifies the vector extension and
a read-only vector operation, then lists models from the configured Ollama endpoint.
It does not start/restart containers, install extensions, load a model or run inference.
Successful output ends with `Lab ready.` and exit code 0. Any failure returns 1.
Docker being Up alone is insufficient: the database connection and vector operation
must also pass. Container identification is a separate check from the configured DSN;
the script does not prove that a container discovered by name is the DSN's server.

Run a lab script only after the checks pass:

```bash
bash lab.sh rag_test.py --help
bash lab.sh rag_test.py --order by-model --out results/rag-new
```

Cloud probes are opt-in and billable (two embedding calls and six LLM calls):

```bash
bash lab.sh --cloud
bash lab.sh --cloud -- rag_test.py --order by-model --out results/rag-new
```

These example RAG commands are dry runs. Add --execute only for the intended measured run.
For a long benchmark, normally run the cloud probes once, then use the launcher without
--cloud on subsequent blocks. Cloud probes use check_cloud.py, not the measured adapter.
The full benchmark smoke test in the main runbook is still required.

## Configuration and failures

- Set `OLLAMA_HOST=http://192.168.178.25:11434` in the VM environment or ai-labs/code/.env
  if that remains the Windows host's address. The check uses the Ollama Python client,
  just like providers.py; it does not hard-code an endpoint different from inference.
  Without OLLAMA_HOST the client uses its own default, normally localhost.
- Set PG_DSN to the existing database connection; do not paste its password into logs.
- Docker automatically detects a running container with postgres/pgvector in its name
  or image. For a custom image/name set `LAB_DB_CONTAINER=your_actual_container_name`.
- Docker errors: run `docker ps -a` and inspect the intended container's state/health.
  Fix daemon availability, permissions or stopped containers using your existing lab setup.
- Database errors: verify host/port/credentials and that the vector extension exists in
  the specific database named in PG_DSN. The startup script makes no database changes.
- Ollama errors: from the VM, try `curl --fail --max-time 10 http://192.168.178.25:11434/api/tags`
  using the actual configured address. Check the Windows service, firewall and IP address.
- Detailed raw connection errors are intentionally not printed by the readiness script.
  Use the relevant runbook checks for diagnosis without sharing keys or full credential DSNs.

Existing .env values are read; exported environment values take precedence.
Checks do not certify table contents, GPU residency, model-specific context size or answer
quality. Continue with the RAG runbook for those validations.

`bash lab.sh` is an automatic preflight for scripts launched through it. Direct
`python rag_test.py` bypasses it. It does not register a cron job, shell-login hook or
desktop scheduled task. With no script argument it checks and exits; its venv activation
does not persist in the parent terminal. For manual work, use `source .venv/bin/activate`.
