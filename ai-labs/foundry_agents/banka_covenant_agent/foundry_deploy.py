"""Deploy the covenant agent as a Foundry hosted agent and call it.

    python foundry_deploy.py deploy-code                 source upload (zip), no container registry; agent covenant-agent-code
    python foundry_deploy.py deploy-code t4              same code plus the attack sets A and F; test agent covenant-agent-t4
    python foundry_deploy.py deploy <acr>.azurecr.io/covenant-agent:<tag>      container image; agent covenant-agent
    python foundry_deploy.py probe <image>               diagnosis: same image, no settings, agent covenant-probe
    python foundry_deploy.py ask C01 2026Q1 [agent-name]  default agent: FOUNDRY_AGENT_NAME or covenant-agent
    python foundry_deploy.py logs <agent-name> [text]    console log of the newest session; text filters the lines

Needs: pip install "azure-ai-projects>=2.3.0" azure-identity   and   az login  (role: Foundry Project Manager).
Non-secret settings come from the environment or .env (same names as the lab). Secrets are NOT read here:
the agent gets them from a Foundry project connection through ${{connections.<name>.credentials.<key>}}
placeholders, which the platform resolves when the sandbox starts.
"""
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")   # local, not committed: the PostgreSQL server (see .env.example)

PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT",
                             "https://stefanbobal-9304-resource.services.ai.azure.com/api/projects/stefanbobal-9304")
AGENT_NAME = os.getenv("FOUNDRY_AGENT_NAME", "covenant-agent")
CODE_AGENT_NAME = "covenant-agent-code"
CONNECTION = os.getenv("FOUNDRY_SECRETS_CONNECTION", "agent-secrets")   # a CustomKeys connection on the project
PG_HOST = os.getenv("AZURE_PG_HOST", "").strip()   # both come from .env; the repository holds no server name
PG_USER = os.getenv("AZURE_PG_USER", "").strip()

# The same files the Dockerfile copies: the server, the chain, and the trusted documents. Nothing else is uploaded.
CODE_FILES = ["foundry_app.py", "agent.py", "config.py", "providers.py", "covenants.py", "sources.py",
              "contract_rules.py", "rag_prompt.py", "search.py", "thresholds.py", "thresholds.json",
              "load_documents.py"]
CODE_RUNTIME = "python_3_13"
# T4 only: the attack sets of the home lab, read in place so both labs attack with identical files. They go into a
# separate test agent, never into the production one.
T4_AGENT_NAME = "covenant-agent-t4"
ATTACK_SETS = {"a": BASE.parent.parent / "code_banka" / "data_attacks_a",
               "f": BASE.parent.parent / "code_banka" / "data_attacks_f"}


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def need(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Set {name} (in the shell or .env)")
    return value


def client():
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    return AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=DefaultAzureCredential())


def pg_dsn():
    """Connection string without a password (libpq reads PGPASSWORD)."""
    if not PG_HOST or not PG_USER:
        raise SystemExit("Set AZURE_PG_HOST and AZURE_PG_USER in .env next to this script (see .env.example)")
    return f"host={PG_HOST} port=5432 user={PG_USER} dbname=postgres sslmode=require"


def agent_env():
    return {
        "PYTHONNOUSERSITE": "1",
        "LLM_PROFILE": "azure",
        "EMBED_PROFILE": "azure",
        "AZURE_OPENAI_ENDPOINT": need("AZURE_OPENAI_ENDPOINT"),
        "AZURE_OPENAI_LLM_DEPLOYMENT": need("AZURE_OPENAI_LLM_DEPLOYMENT"),
        "AZURE_OPENAI_EMBED_DEPLOYMENT": need("AZURE_OPENAI_EMBED_DEPLOYMENT"),
        "AZURE_OPENAI_API_KEY": "${{connections.%s.credentials.openai_key}}" % CONNECTION,
        # libpq reads the password from PGPASSWORD, so the DSN itself holds no secret
        "PG_DSN": pg_dsn(),
        "PGPASSWORD": "${{connections.%s.credentials.pg_password}}" % CONNECTION,
    }


def wait_active(project, name, version):
    log(f"version {version} of {name} created, waiting for status active")
    started = time.time()
    while True:
        info = project.agents.get_version(agent_name=name, agent_version=version)
        status = info["status"]
        log(f"status: {status} ({int(time.time() - started)}s)")
        if status == "active":
            return 0
        if status == "failed":
            log(f"provisioning failed: {info.get('error')}")
            return 1
        time.sleep(5)


def protocols():
    from azure.ai.projects.models import AgentEndpointProtocol, ProtocolVersionRecord
    return [ProtocolVersionRecord(protocol=AgentEndpointProtocol.RESPONSES, version="2.0.0")]


def deploy(image, probe=False):
    """probe=True: a separate agent (covenant-probe) with no settings and no connection placeholders. The server
    starts without them, so this tells a platform problem (probe fails too) from a configuration problem."""
    from azure.ai.projects.models import ContainerConfiguration, HostedAgentDefinition
    name = "covenant-probe" if probe else AGENT_NAME
    env = {"PYTHONNOUSERSITE": "1"} if probe else agent_env()
    log(f"creating a version of {name} from {image}")
    project = client()
    agent = project.agents.create_version(
        agent_name=name,
        definition=HostedAgentDefinition(protocol_versions=protocols(), cpu="1", memory="2Gi",
                                         container_configuration=ContainerConfiguration(image=image),
                                         environment_variables=env),
    )
    return wait_active(project, name, agent.version)


def build_zip(attack_sets=()):
    """Flat zip (no wrapper folder): the chain, data/, and requirements.txt for the platform's remote build.
    attack_sets: keys of ATTACK_SETS; only their companies/ documents are added (not the expected answers)."""
    buffer = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name in CODE_FILES:
            z.write(BASE / name, name)
            count += 1
        z.write(BASE / "requirements-foundry.txt", "requirements.txt")
        for path in sorted((BASE / "data").rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(BASE).as_posix())
                count += 1
        for key in attack_sets:
            root = ATTACK_SETS[key]
            if not (root / "companies").is_dir():
                raise SystemExit(f"{root} is missing; build it in code_banka with generate_attacks.py")
            for path in sorted((root / "companies").rglob("*.md")):
                z.write(path, f"{root.name}/{path.relative_to(root).as_posix()}")
                count += 1
    return buffer.getvalue(), count + 1


def deploy_code(t4=False):
    """No image and no registry: the platform installs requirements.txt and runs python foundry_app.py.
    t4=True: the same code as a separate agent that also holds the attack sets A and F."""
    from azure.ai.projects.models import CodeConfiguration, HostedAgentDefinition
    name = T4_AGENT_NAME if t4 else CODE_AGENT_NAME
    env = agent_env()
    if t4:
        env["COVENANT_DATA_DIRS"] = ",".join(["data"] + [ATTACK_SETS[k].name for k in ATTACK_SETS])
    data, count = build_zip(tuple(ATTACK_SETS) if t4 else ())
    digest = hashlib.sha256(data).hexdigest()
    log(f"zip: {count} files, {len(data) // 1024} KiB, sha256 {digest[:16]}")
    log(f"creating a version of {name} from source ({CODE_RUNTIME}, remote build)")
    project = client()
    agent = project.agents.create_version_from_code(
        agent_name=name,
        definition=HostedAgentDefinition(
            protocol_versions=protocols(), cpu="1", memory="2Gi",
            code_configuration=CodeConfiguration(runtime=CODE_RUNTIME, entry_point=["python", "foundry_app.py"],
                                                 dependency_resolution="remote_build"),
            environment_variables=env,
        ),
        code=("agent-code.zip", data, "application/zip"),
        code_zip_sha256=digest,
        description="Covenant agent, architecture A (source upload)" + (", T4 test agent with attack sets" if t4 else ""),
    )
    return wait_active(project, name, agent.version)


def ask(company_id, period, name):
    log(f"asking {name}: {company_id} {period}")
    response = client().get_openai_client(agent_name=name).responses.create(input=f"{company_id} {period}")
    try:
        out = json.loads(response.output_text)
        print(json.dumps(out, ensure_ascii=False, indent=1))
    except ValueError:
        print(response.output_text)
    return 0


def logs(name, only=None, seconds=12):
    """Console log of the newest session of the agent (the stream replays from container start, then follows).
    only: print just the lines that contain this text, e.g. env-check."""
    import urllib.request
    from azure.identity import DefaultAzureCredential
    sessions = [dict(s) for s in client().agents.list_sessions(name)]
    if not sessions:
        raise SystemExit(f"{name} has no session yet; call it first with: ask C01 2026Q1 {name}")
    session = max(sessions, key=lambda s: s.get("created_at", 0))   # the service lists the oldest first
    version = session["version_indicator"]["agent_version"]
    log(f"{name} version {version}, session {session['agent_session_id'][:12]}..., reading for {seconds}s")
    token = DefaultAzureCredential().get_token("https://ai.azure.com/.default").token
    url = (f"{PROJECT_ENDPOINT}/agents/{name}/versions/{version}/sessions/{session['agent_session_id']}"
           ":logstream?api-version=v1")
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "Accept": "text/event-stream"})
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=seconds) as stream:
            for raw in stream:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("data:"):
                    try:
                        message = json.loads(line[5:]).get("message", "")
                    except ValueError:
                        message = line[5:]
                    if message.strip() and "/readiness" not in message and (not only or only in message):
                        print(message)
                if time.time() - started > seconds:
                    break
    except TimeoutError:
        pass   # the stream stays open while the session lives; a quiet period ends the read
    return 0


def main(argv):
    if argv == ["deploy-code"]:
        return deploy_code()
    if argv == ["deploy-code", "t4"]:
        return deploy_code(t4=True)
    if len(argv) in (2, 3) and argv[0] == "logs":
        return logs(argv[1], argv[2] if len(argv) == 3 else None)
    if len(argv) == 2 and argv[0] == "deploy":
        return deploy(argv[1])
    if len(argv) == 2 and argv[0] == "probe":
        return deploy(argv[1], probe=True)
    if len(argv) in (3, 4) and argv[0] == "ask":
        return ask(argv[1], argv[2], argv[3] if len(argv) == 4 else AGENT_NAME)
    raise SystemExit(__doc__)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
