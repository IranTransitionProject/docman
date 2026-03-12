# Setting Up Docman on Windows 11

A step-by-step guide to setting up the Docman development environment from scratch on a brand-new Windows 11 PC.

No prior developer experience is assumed. If you already have some of these tools installed, skip those steps.

---

## What you'll end up with

- **Python 3.13** — the programming language everything runs on
- **Git** — version control for downloading and contributing to the code
- **Docker Desktop** — runs NATS (message broker) and Redis (data store) in containers
- **Ollama** — runs AI models locally on your PC
- **Loom** — the orchestration framework
- **Docman** — the document processing pipeline you'll be testing

Total time: roughly 45–60 minutes (depending on your internet speed).

---

## Before you start

### Check your Windows version

1. Press **Win + I** to open Settings
2. Go to **System → About**
3. Look for **Edition**: you need Windows 11 (Home, Pro, or Education all work)
4. Look for **OS build**: you need 22631 or higher

### Know your processor type

Most Windows PCs use Intel or AMD processors (x64). Some newer devices (Surface Pro, Copilot+ PCs) use ARM-based Snapdragon processors. This guide covers both, with notes where they differ.

To check: in **System → About**, look at **System type** — it will say either "x64-based processor" or "ARM-based processor".

---

## Step 1: Open Terminal

Windows Terminal is the modern command-line application for Windows 11.

1. Press **Win + X** (or right-click the Start button)
2. Click **Terminal** (or **Terminal (Admin)** if available)

You should see a PowerShell window with a blinking cursor. This is where you'll type all commands.

> **If you don't see Terminal:** Open the Microsoft Store, search for "Windows Terminal", and install it.

> **Important:** Some commands in this guide need administrator access. If a command fails with "Access denied", close Terminal and reopen it by right-clicking the Start button and choosing **Terminal (Admin)**.

---

## Step 2: Enable developer tools (winget)

`winget` is Windows' built-in package manager. It should already be available on Windows 11. Verify:

```powershell
winget --version
```

If you see a version number (like `v1.9.x`), you're good. If not:

1. Open the **Microsoft Store**
2. Search for **App Installer** (by Microsoft)
3. Install or update it

---

## Step 3: Install Git

```powershell
winget install --id Git.Git -e --source winget
```

**Close and reopen Terminal** so Git is available in your PATH. Then verify:

```powershell
git --version
```

You should see `git version 2.x.x.windows.x`.

---

## Step 4: Install Python 3.13

```powershell
winget install -e --id Python.Python.3.13
```

**Close and reopen Terminal** again. Then verify:

```powershell
python --version
```

You should see `Python 3.13.x`.

> **Note:** On Windows, the command is `python` (not `python3` as on macOS/Linux).

> **If you see the Microsoft Store open instead:** Windows sometimes redirects the `python` command to the Store. After installing Python via winget, close Terminal completely, reopen it, and try again.

---

## Step 5: Install Docker Desktop

Docker Desktop runs containers (small isolated environments) on your PC. We use it for NATS and Redis.

### 5a: Enable WSL2

Docker Desktop needs WSL2 (Windows Subsystem for Linux). Open Terminal **as Administrator** and run:

```powershell
wsl --install
```

This installs WSL2 and Ubuntu. **Restart your computer** when prompted.

After restarting, Ubuntu may open a window asking you to create a username and password. You can set these to anything simple — they're only for the Linux subsystem, not your Windows account.

### 5b: Install Docker Desktop

```powershell
winget install Docker.DockerDesktop
```

After installation:

1. **Open Docker Desktop** from the Start menu
2. Accept the license agreement
3. Wait for it to finish starting (you'll see "Docker Desktop is running" in the system tray)

> **Note for ARM/Snapdragon PCs:** Docker Desktop on ARM is in early access. It works but you may encounter occasional issues with certain container images. If a container fails to start, try pulling the ARM-specific image tag (e.g., `nats:2.10-alpine` usually has ARM support built in).

Verify Docker works:

```powershell
docker --version
docker run hello-world
```

---

## Step 6: Install Ollama

Ollama runs AI models locally on your PC.

1. Go to [ollama.com/download/windows](https://ollama.com/download/windows)
2. Download and run **OllamaSetup.exe**
3. Follow the installer — it doesn't need administrator rights

After installation, Ollama runs in the background (you'll see its icon in the system tray near the clock).

Open a **new Terminal window** and download the AI model:

```powershell
ollama pull command-r7b:latest
```

This downloads about 5 GB. Wait for it to complete.

Verify it works:

```powershell
ollama list
```

You should see `command-r7b:latest` in the list.

> **GPU acceleration:** If you have an NVIDIA graphics card, Ollama will automatically use it for faster inference. AMD Radeon GPUs are also supported. Intel and Snapdragon GPUs are not currently supported by Ollama — it will fall back to CPU, which is slower but still works.

---

## Step 7: Start infrastructure containers

Make sure Docker Desktop is running (check for its icon in the system tray), then:

```powershell
docker run -d --name loom-nats -p 4222:4222 nats:2.10-alpine
docker run -d --name loom-redis -p 6379:6379 redis:7-alpine
```

Verify they're running:

```powershell
docker ps
```

You should see two containers: `loom-nats` and `loom-redis`.

> **Note:** These containers stop when you restart your PC or close Docker Desktop. To start them again:
> ```powershell
> docker start loom-nats loom-redis
> ```

---

## Step 8: Get the project code

Create a directory for the project and clone the repositories:

```powershell
mkdir C:\Dev\IranTransitionProject
cd C:\Dev\IranTransitionProject

git clone https://github.com/IranTransitionProject/loom.git
git clone https://github.com/IranTransitionProject/docman.git
git clone https://github.com/IranTransitionProject/framework.git
```

> **Note:** If these are private repositories, you'll need to authenticate with GitHub first:
> ```powershell
> winget install GitHub.cli
> gh auth login
> ```
> Follow the prompts to log in with your GitHub account.

---

## Step 9: Create a Python virtual environment

A virtual environment keeps this project's dependencies separate from your system Python.

```powershell
cd C:\Dev\IranTransitionProject
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Your terminal prompt should now show `(.venv)` at the beginning. This means the virtual environment is active.

> **If you get an error about "execution of scripts is disabled":** Run this command first and then try again:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

> **Important:** Every time you open a new Terminal window to work on this project, activate the virtual environment:
> ```powershell
> cd C:\Dev\IranTransitionProject
> .venv\Scripts\Activate.ps1
> ```

---

## Step 10: Install Loom and Docman

With the virtual environment active:

```powershell
# Install Loom (the framework) with local model support
pip install -e "loom[dev,local]"

# Install Docman (the test project) with dev tools
pip install -e "docman[dev]"
```

This will download and install many packages (including PyTorch for document processing). This is the longest step — it may take 10–15 minutes.

> **Note for NVIDIA GPU owners:** By default, pip installs CPU-only PyTorch on Windows. To enable GPU acceleration for Docling's document layout detection, install the CUDA version instead:
> ```powershell
> pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
> ```
> Run this *before* `pip install -e "docman[dev]"`. If you don't have an NVIDIA GPU, skip this — CPU works fine, just slower.

Verify installation:

```powershell
loom --help
```

You should see a list of Loom commands: `worker`, `processor`, `pipeline`, `router`, `submit`.

---

## Step 11: Download Docling detection models

Docling uses AI models for document layout detection. Pre-download them:

```powershell
docling-tools models download
```

This downloads a few hundred MB. They're cached in your user profile under `.cache\docling\models\`.

---

## Step 12: Run the tests

Verify everything is installed correctly:

```powershell
# Test Loom
cd C:\Dev\IranTransitionProject\loom
pytest tests/ -v --ignore=tests/test_integration.py

# Test Docman
cd C:\Dev\IranTransitionProject\docman
pytest tests/ -v
```

All tests should pass (green). The Loom integration test is excluded because it needs the full pipeline running.

---

## Step 13: Run the full pipeline

### 13a: Set environment variables

```powershell
cd C:\Dev\IranTransitionProject\docman

$env:NATS_URL = "nats://localhost:4222"
$env:OLLAMA_URL = "http://localhost:11434"
$env:OLLAMA_MODEL = "command-r7b:latest"
```

### 13b: Create a test workspace

```powershell
mkdir C:\temp\docman-workspace -Force
```

If you have a PDF you'd like to test with, copy it there:

```powershell
Copy-Item "$HOME\Downloads\your-document.pdf" C:\temp\docman-workspace\
```

### 13c: Start the pipeline

```powershell
.\scripts\dev-start.ps1
```

This starts all five pipeline components in the background: router, extractor, classifier, summarizer, and pipeline orchestrator.

### 13d: Submit a test document

```powershell
.\scripts\dev-start.ps1 -Action submit -File test_report.pdf
```

### 13e: Watch the logs

```powershell
Get-Content .dev-pids\*.log -Tail 30 -Wait
```

Press **Ctrl + C** to stop watching logs.

### 13f: Stop the pipeline

```powershell
.\scripts\dev-start.ps1 -Action stop
```

---

## Common tasks

### Adding a new worker

Workers are defined by YAML configuration files. To create a new one:

1. Copy an existing worker config:
   ```powershell
   Copy-Item configs\workers\doc_classifier.yaml configs\workers\my_new_worker.yaml
   ```
2. Edit the file in any text editor (Notepad, VS Code, etc.) to define your worker's system prompt, input/output schemas, and behavior
3. Start it:
   ```powershell
   loom worker --config configs\workers\my_new_worker.yaml --tier local --nats-url nats://localhost:4222
   ```

See `loom\configs\workers\_template.yaml` for a blank template with documentation.

### Adding a new processing backend

Processing backends handle non-LLM tasks (like document extraction). To create one:

1. Create a new Python file in `docman\src\docman\backends\`
2. Implement the `ProcessingBackend` interface from Loom
3. Reference it in a worker config:
   ```yaml
   processing_backend: "docman.backends.my_backend.MyBackend"
   ```

See `docman\src\docman\backends\docling_backend.py` for an example.

### Modifying the pipeline

Pipeline stages are defined in `configs\orchestrators\doc_pipeline_local.yaml`. You can:

- Reorder stages
- Add new stages that reference your workers
- Change input mappings to pass data between stages

### Trying a different Ollama model

```powershell
# See available models
ollama list

# Pull a new model
ollama pull llama3.2:3b

# Set it as the active model
$env:OLLAMA_MODEL = "llama3.2:3b"

# Restart the pipeline
.\scripts\dev-start.ps1 -Action stop
.\scripts\dev-start.ps1
```

---

## Key differences from macOS

If you're switching between a Mac and a Windows setup, here are the important differences:

| What | macOS | Windows |
|------|-------|---------|
| Terminal command | `python3` | `python` |
| Activate venv | `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
| Path separator | `/` (forward slash) | `\` (backslash) |
| Startup script | `./scripts/dev-start.sh` | `.\scripts\dev-start.ps1` |
| Extractor config | `doc_extractor.yaml` (MPS GPU) | `doc_extractor_windows.yaml` (CPU) |
| OCR engine | `ocrmac` (macOS native) | `easyocr` (cross-platform) |
| GPU acceleration | MPS (Metal, automatic) | CUDA (NVIDIA only, needs manual PyTorch install) |
| Container runtime | OrbStack (recommended) | Docker Desktop (requires WSL2) |
| Workspace path | `/tmp/docman-workspace` | `C:\temp\docman-workspace` |

---

## Troubleshooting

### "python is not recognized" or opens the Microsoft Store

Close Terminal completely. Reopen it and try `python --version` again. If it still doesn't work, check that Python is in your PATH:

```powershell
where.exe python
```

If nothing shows up, you may need to add Python to your PATH manually. Open **Settings → System → About → Advanced system settings → Environment Variables**, and add Python's install directory to the `Path` variable.

### "execution of scripts is disabled"

Run this once:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### "loom is not recognized"

Make sure your virtual environment is active (you should see `(.venv)` in your prompt). If it is active and `loom` still isn't found:

```powershell
pip install -e "C:\Dev\IranTransitionProject\loom[dev,local]"
```

### Docker Desktop won't start

- Make sure virtualization is enabled in your BIOS/UEFI settings (usually under "Advanced" or "CPU Configuration" — look for "Intel VT-x" or "AMD-V" or "SVM Mode")
- Make sure WSL2 is installed: `wsl --status`
- Restart your computer after enabling virtualization

### Ollama model runs very slowly

- If you don't have an NVIDIA GPU, Ollama runs on CPU which is slower. Models under 8B parameters (like `command-r7b:latest` at 7B) are recommended for CPU-only setups.
- Close other memory-heavy applications
- Make sure at least 8 GB of RAM is free

### "ModuleNotFoundError" when running tests

Make sure you installed both packages in editable mode (Step 10) and that your virtual environment is active.

### Container images fail on ARM/Snapdragon PCs

Most official Docker images include ARM support, but some community images don't. If `docker run` fails with an error mentioning "platform" or "architecture", check if an ARM-specific tag exists for that image.

---

## Architecture overview

For those who want to understand how the pieces fit together:

```
You submit a document (PDF/DOCX)
        |
        v
+---------------+     NATS message bus
|   Pipeline    |<--------------------->  Coordinates the 3 stages
| Orchestrator  |
+-------+-------+
        | Stage 1: extract
        v
+---------------+
|   Extractor   |  DoclingBackend reads PDF -> extracts text, tables, structure
|  (Processor)  |  Writes extracted JSON to workspace
+-------+-------+
        | Stage 2: classify
        v
+---------------+
|  Classifier   |  LLM (Ollama) classifies document type from extracted text
| (LLM Worker)  |  Returns: document_type, confidence, reasoning
+-------+-------+
        | Stage 3: summarize
        v
+---------------+
|  Summarizer   |  LLM (Ollama) produces structured summary
| (LLM Worker)  |  Returns: summary, key_points, word_count
+---------------+
```

All communication happens through NATS messages. Workers are stateless — they process one task at a time and reset. The router determines which worker handles each task based on deterministic rules (no AI involved in routing).
