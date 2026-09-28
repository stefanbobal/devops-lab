# AI Lab 01 – Local LLM with Ollama (hybrid setup)

## Goal

Run a local LLM on the Windows host GPU and call it from the Ubuntu VM over the network.

## Architecture

```
Ubuntu VM (192.168.178.110)                 Windows host (192.168.178.25)
Python scripts, Docker, PostgreSQL  ──────►  Ollama :11434  ──►  RTX 4090 (24 GB VRAM)
```

VirtualBox cannot pass the GPU into the VM, so the model runs on Windows and the VM uses it
as a network service. This is the same pattern as a model endpoint in production:
the model is a separate service, the application calls it over HTTP.

## Concepts

- **Model size vs. VRAM:** a model has billions of parameters, each stored as a number.
- **Quantization:** storing parameters with lower precision. A 70B model needs ~140 GB in FP16,
  ~70 GB in 8-bit and ~35–40 GB in 4-bit. `gemma3:27b` in Ollama is 4-bit (~17 GB) and fits
  into 24 GB VRAM; a 70B model does not.
- **Embedding model:** a small model that turns text into a vector (used from Lab 02 on).

## Steps

### 1. Install Ollama on Windows

Download from ollama.com and install. Verify in PowerShell:

```powershell
ollama --version
```

### 2. Pull models (Windows)

```powershell
ollama pull gemma3:27b
ollama pull nomic-embed-text
```

### 3. Test locally (Windows)

```powershell
ollama run gemma3:27b
```

Ask a question, exit with `/bye`. In a second window run `ollama ps`:
the PROCESSOR column must show **100% GPU**.

### 4. Expose Ollama to the network (Windows)

Option A: Ollama app → Settings → **Expose Ollama to the network**.

Option B:

```powershell
setx OLLAMA_HOST 0.0.0.0
Get-Process *ollama* | Stop-Process -Force
# start Ollama again from the Start menu
```

Verify in a **new** PowerShell window:

```powershell
netstat -an | findstr 11434
```

Expected: `0.0.0.0:11434 ... LISTENING`.

### 5. Firewall (Windows, PowerShell as administrator)

```powershell
New-NetFirewallRule -DisplayName "Ollama" -Direction Inbound -LocalPort 11434 -Protocol TCP -Action Allow -Profile Private
Get-NetConnectionProfile
```

`NetworkCategory` of the Ethernet adapter must be `Private`.

### 6. Test from the VM

```bash
curl http://192.168.178.25:11434
```

Expected: `Ollama is running`.

### 7. Persist OLLAMA_HOST in the VM

The `ollama` Python library reads this variable, so no script needs the IP hard-coded.

```bash
echo 'export OLLAMA_HOST=http://192.168.178.25:11434' >> ~/.bashrc
source ~/.bashrc
```

### 8. Python environment (VM)

```bash
cd ~/devops-lab/ai-labs/code
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `netstat` shows `127.0.0.1:11434` | Ollama did not pick up `OLLAMA_HOST` | Kill all Ollama processes, start again |
| `curl` hangs / timeout | Windows firewall, network profile `Public` | `Set-NetConnectionProfile -InterfaceAlias "Ethernet" -NetworkCategory Private` |
| `curl` connection refused | Ollama not listening on the network | See step 4 |
| Worked yesterday, not today | Windows got a new IP from DHCP | Fritz!Box: always assign the same IPv4 address |
| `ollama ps` shows CPU | Model too big for VRAM | Use a smaller model |

## Experiment

Pull `gemma3:12b` and compare speed and answer quality with `gemma3:27b` on the same question.

## Notes

-
