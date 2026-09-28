# AI Lab 08 – Serving models with vLLM

## Goal

Run a model with vLLM, a production-grade inference server, and compare it with Ollama.

## Concepts

- **Inference server:** a service that loads a model and answers requests over HTTP.
- **OpenAI-compatible API:** most tools speak this API, so one server works with many clients.
- **Batching:** serving many users at once efficiently. This is where vLLM beats Ollama.
- **Model formats and quantization for vLLM:** why vLLM uses different model files than Ollama.

## What you will do

- Run vLLM in Docker on the Windows host with GPU access (Docker Desktop + WSL2 backend).
  VirtualBox cannot access the GPU, so vLLM runs on the host, like Ollama.
- Serve one model that fits into 24 GB VRAM.
- Call it from the VM with `curl` and from Python.
- Send 10 requests in parallel to Ollama and to vLLM and compare total time.

## Done when

- [ ] vLLM answers requests from the VM
- [ ] I can explain the difference between Ollama and vLLM in two sentences
- [ ] Parallel request comparison is in the Notes section

## Notes

-
