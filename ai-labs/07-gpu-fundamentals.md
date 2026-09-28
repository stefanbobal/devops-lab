# AI Lab 07 – GPU fundamentals and nvidia-smi

## Goal

Understand what happens on the GPU when a model runs, and read the numbers that matter.

## Concepts

- **VRAM:** GPU memory. It holds the model weights plus the working memory for requests.
- **KV cache:** the working memory for the conversation context. Longer context and more
  parallel users = more KV cache = more VRAM.
- **Utilization, temperature, power draw:** the basic health signals of a GPU.
- **Driver and CUDA version:** the software layer between the model server and the GPU.

## What you will do

- Read `nvidia-smi` output field by field while idle, while a model is loaded and during generation.
- Load models of different sizes in Ollama and watch VRAM usage change.
- Increase the context length and observe the effect on VRAM.
- Record a simple table: model, size, VRAM used, tokens per second.

## Done when

- [ ] I can explain every field in `nvidia-smi` output
- [ ] I can explain why a 27B model uses more VRAM than its file size
- [ ] My measurement table is in the Notes section

## Notes

-
