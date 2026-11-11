# cert_agent: certificate renewal agent (SAP and non-SAP)

**Status (2026-11-11):** the workflow, the Jira client, the certificate checks and the MCP
server are written and tested here with stand-ins. Nothing has run against a real SAP
system, a real Jira or the real Cloud Run service yet. See
[What is tested and what is not](#what-is-tested-and-what-is-not).

This is a generic design. Do not put real hostnames, SIDs, ticket keys or company names
into this folder. Real values belong in `.env` and `inventory.yaml`, which are git-ignored.

## What it does

1. Reads the certificates listed in the inventory and their expiry dates.
2. When one is due, creates a CSR on the target system (the key stays there).
3. Opens a Jira ticket and attaches the CSR.
4. Picks up the signed certificate that the PKI team attaches to the same ticket.
5. Checks it, waits for a person to approve, installs it, and verifies that the system
   really serves it. If not, it puts the old certificate back.

Targets: SAP ABAP (STRUST), SAP Java (NWA), BOBJ and Google Cloud load balancer.

## How it is built

One deterministic workflow. A language model is not needed to run it; the model sits on
top, through the MCP server, to answer questions and trigger steps.

| Part | File | Role |
|---|---|---|
| Requester job | `requester.py` | Scheduled. Finds due certificates, creates CSR and ticket. |
| Installer job | `installer.py` | Scheduled. Goes through open tickets, validates, installs, verifies. |
| MCP server | `mcp_server.py` | The same steps as five tools for an agent. |
| Agent prompt | `AGENT_INSTRUCTIONS.md` | System prompt for the agent that uses the tools. |
| Workflow | `workflow.py` | All rules and checks. Jobs and MCP tools both call this. |
| Certificate checks | `certcheck.py`, `tlscheck.py` | Validate a signed certificate; read what a host serves. |
| Jira | `jira_client.py` | REST API v2 with a personal access token. |
| Drivers | `drivers/` | One per target type: read certificate, create CSR, install. |
| ABAP | `abap/z_cert_agent.abap` | Three RFC function modules the ABAP driver calls. |

Target types in the inventory:

| Type | Reads the certificate | Creates the CSR | Installs |
|---|---|---|---|
| `abap` | RFC: own certificate of the PSE | RFC, for the existing key | RFC: import response, save, distribute, notify ICM |
| `java_nwa` | TLS handshake on the endpoint | Playwright: Generate CSR Request | Playwright: Import CSR Response |
| `cloudrun` (BOBJ, load balancer) | TLS handshake on the endpoint | Call to the existing Cloud Run service | Call to the existing Cloud Run service |
| `fake` | A local directory | Locally | Locally. For tests and for trying things out. |

The agent watches the certificates you list in the inventory. It does not search a system
for all PSEs on its own.

## The ticket is the state of record

One ticket per certificate. The agent keeps its state in labels:

| Label | Meaning |
|---|---|
| `cert-agent` | The ticket belongs to the agent. |
| `cert-fp-<16 hex>` | Fingerprint of the certificate being replaced. Prevents a second ticket. |
| `cert-validated` | The attached certificate passed all checks. |
| `cert-installed` | Installed and verified. |
| `cert-failed` | The agent stopped. A person must look, then remove the label to retry. |

A person approves an install by moving the ticket to a status listed in
`JIRA_APPROVED_STATUSES`. Targets with `approval_required: false` (sandboxes) skip this.

## Safety rules, as implemented

- **Private keys stay on the target.** Drivers only hand out CSRs and take certificates.
- **A signed certificate is accepted only if** it has the key of the CSR, covers the CSR's
  DNS names, is valid long enough, and chains to a CA in `CERT_AGENT_TRUSTED_CAS`.
  Who attached the file does not matter.
- **The ticket cannot redirect an install.** The agent attaches a small metadata file
  signed with `CERT_AGENT_HMAC_KEY`. A changed metadata file or a changed CSR stops the
  ticket.
- **Checks against the live target before the install:** the installed certificate is
  still the one from the request, the new one has the same key (where the key is reused),
  it expires later, and the endpoint in the inventory serves what the target reports.
- **Verify after the install,** by TLS handshake. On failure the old certificate is
  re-installed where the key was reused (ABAP, Java), and the ticket is marked failed.
- **No credentials reach the model.** Passwords come from environment variables named in
  the inventory. The MCP tools return states and public certificate facts only.
- **The ABAP function modules refuse every PSE except the SSL server PSE,** whatever the
  caller asks for.

## Set up

```bash
cd ai-labs
python3 -m venv cert_agent/.venv && source cert_agent/.venv/bin/activate
pip install -r cert_agent/requirements.txt
cp cert_agent/.env.example cert_agent/.env                      # fill in
cp cert_agent/inventory.example.yaml cert_agent/inventory.yaml  # fill in
# put the PEM certificates of your issuing CAs into cert_agent/trusted_cas.pem
```

In Jira you need: a technical user with a personal access token, a project for the
tickets, the Labels field on the create and edit screens, and an approval status that
only approvers can move a ticket to.

## Run

All commands run from the folder that contains `cert_agent/`. Progress is printed to
stderr with timestamps; the result is JSON on stdout.

```bash
python -m pytest cert_agent/tests -q            # the tests, about 10 seconds

python -m cert_agent.requester --dry-run        # report only
python -m cert_agent.requester                  # create CSRs and tickets where due
python -m cert_agent.installer --dry-run        # report only, writes nothing to Jira
python -m cert_agent.installer                  # validate, install approved tickets
python -m cert_agent.installer --ticket CERT-12

python -m cert_agent.mcp_server                 # MCP over stdio
MCP_TRANSPORT=streamable-http python -m cert_agent.mcp_server
```

MCP tools: `list_certificates`, `find_cert_tickets`, `request_renewal`, `check_ticket`,
`install_ticket`. Each runs a complete checked step, so the model cannot skip the
validation or the approval.

## What is tested and what is not

Tested here (61 tests, plus one run of the real jobs against a stand-in Jira over HTTP):

- certificate parsing and validation, including wrong key, untrusted CA, forged issuer
  name, short validity and missing names;
- the whole workflow with a fake target: request, no duplicate ticket, rejection,
  approval gate, install, verification, rollback, tampered ticket files;
- the Jira client against a local server that answers like the REST API v2;
- the TLS check against a local TLS server;
- the MCP server over stdio, with versions 1.30 and 2.3 of the `mcp` library.

Not tested, because the real systems were not available:

| Part | State | First thing to do |
|---|---|---|
| `abap/z_cert_agent.abap` | Never activated. Written from memory of STRUST. | Work through the four VERIFY points in the file header on a sandbox. |
| `drivers/abap.py` | Tested only against a stand-in for `pyrfc`. | Run `requester --dry-run` against the sandbox once the function group exists. |
| `drivers/java_nwa.py` | Never run. Page address, field names and button texts are from memory. | Run with `headless: false` and correct the constants at the top of the file. |
| `drivers/cloudrun.py` | Tested against an assumed contract (`/csr`, `/install`). | Adapt the two calls to the real service. |
| `jira_client.py` | Never run against a real Jira. | Run `installer --dry-run`; it only reads. |

## Decisions (2026-11-11)

| Topic | Decision | Consequence |
|---|---|---|
| Jira | Self-hosted Jira (Data Center) | REST API v2 with a personal access token of a technical user |
| Jira access for the agents | Not through the existing OAuth2-only MCP server | The agent's own MCP server calls the REST API directly |
| Key on renewal | Reusing the existing key is allowed | CSR on the existing PSE; rollback needs no key backup |
| ABAP access | A small Z function group is allowed | Three RFC function modules |
| Signed certificate | Attached to the same Jira ticket | Jira is the only intake channel; no email monitoring |
| Model | Supplied by the agent platform | No model code here; the agent connects to the MCP server |

## Open items

- Confirm that personal access tokens are enabled in Jira and a technical user may have one.
- Verify and activate the ABAP function group on a sandbox.
- Check that `pyrfc` and the SAP NW RFC SDK are allowed in the target environment.
- Get the real interface of the Cloud Run service and adapt `drivers/cloudrun.py`.
- Confirm that the BOBJ certificate is the Tomcat keystore one.
- SAN support: older releases cannot put alternative names into a STRUST request.
