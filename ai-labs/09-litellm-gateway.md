# AI Lab 09 – LiteLLM gateway

## Goal

Put one gateway in front of all models, so users get one endpoint and one API key,
and I control access, routing and usage.

## Concepts

- **Gateway:** a single entry point that forwards requests to the right model backend.
- **Virtual API keys:** one key per team or user, revocable, with limits.
- **Routing and fallback:** send a request to vLLM, fall back to Ollama if vLLM is down.
- **Usage reporting:** who used which model, how many tokens, when.

## What you will do

- Run LiteLLM in Docker in the VM, with its PostgreSQL database.
- Register both backends: vLLM and Ollama.
- Create API keys for two fictional teams ("sap-ops", "dev") with different limits.
- Stop vLLM and verify the fallback works.
- Produce a usage report per team.

## Done when

- [ ] Both teams can call models only with their own key
- [ ] A team hitting its limit gets a clear error
- [ ] Fallback works when one backend is down
- [ ] I can show token usage per team

## Notes

-
