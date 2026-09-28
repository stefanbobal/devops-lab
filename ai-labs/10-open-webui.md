# AI Lab 10 – Open WebUI

## Goal

Give users a ChatGPT-like web interface on top of the platform, without direct access to backends.

## Concepts

- **Front end vs. gateway:** the UI talks only to LiteLLM, never directly to vLLM or Ollama.
- **Users and roles:** admin vs. regular user.
- **Self-service:** users should not need me to start using the platform.

## What you will do

- Run Open WebUI in Docker in the VM, connected to LiteLLM.
- Create an admin and two regular users.
- Decide which models regular users can see.
- Upload a fictional runbook and ask questions about it (built-in RAG).

## Done when

- [ ] Users log in and chat without knowing where the model runs
- [ ] Model visibility is controlled by the admin
- [ ] Requests from Open WebUI appear in the LiteLLM usage report

## Notes

-
