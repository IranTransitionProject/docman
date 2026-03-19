# Setting Up Docman on macOS (Apple Silicon)

A step-by-step guide to setting up the Docman development environment from scratch on a brand-new Apple Silicon Mac (M1, M2, M3, M4 — any model).

No prior developer experience is assumed. If you already have some of these tools installed, skip those steps.

---

## What you'll end up with

- **Python 3.13** — the programming language everything runs on
- **uv** — fast Python package manager (replaces pip and venv)
- **Git** — version control for downloading and contributing to the code
- **OrbStack** — lightweight container runtime (runs NATS message broker and Redis)
- **Ollama** — runs AI models locally on your Mac
- **Loom** — the orchestration framework
- **Docman** — the document processing pipeline you'll be testing

Total time: roughly 30–45 minutes (depending on your internet speed).

---

## Step 1: Open Terminal

Terminal is the command-line application built into every Mac.

1. Press **Cmd + Space** to open Spotlight
2. Type **Terminal** and press Enter

You'll see a window with a blinking cursor. This is where you'll type all the commands in this guide.

> **Tip:** Keep Terminal open for the entire setup. You can paste commands by pressing **Cmd + V**.

---

## Step 2: Install Homebrew

Homebrew is the standard package manager for macOS. It installs developer tools with simple commands.

Paste this into Terminal and press Enter:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

It will ask for your Mac password (the one you use to log in). Type it — **you won't see characters appear**, that's normal — and press Enter.

When it finishes, it will show instructions to add Homebrew to your PATH. Run the commands it displays. They will look something like:

```bash
echo >> ~/.zprofile
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Verify it worked:

```bash
brew --version
```

You should see something like `Homebrew 4.x.x`.

---

## Step 3: Install Python, Git, uv, and basic tools

```bash
brew install python@3.13 git uv
```

Verify both installed:

```bash
python3 --version
git --version
```

You should see `Python 3.13.x` and `git version 2.x.x`.

---

## Step 4: Install OrbStack (container runtime)

OrbStack is a fast, lightweight alternative to Docker Desktop, optimized for Apple Silicon.

```bash
brew install orbstack
```

After installation, open OrbStack once to complete its setup:

```bash
open -a OrbStack
```

A window will appear. Follow the on-screen prompts (it takes about a minute). Once OrbStack is running, you'll see its icon in the menu bar at the top of your screen.

Verify Docker commands work:

```bash
docker --version
```

---

## Step 5: Install Ollama

Ollama runs AI models locally on your Mac.

```bash
brew install ollama
```

Start the Ollama service:

```bash
ollama serve &
```

> **Note:** `ollama serve &` runs Ollama in the background. Alternatively, you can download the Ollama desktop app from [ollama.com](https://ollama.com) which starts automatically.

Download the AI model we'll use for testing:

```bash
ollama pull command-r7b:latest
```

This downloads about 5 GB. Wait for it to complete.

Verify it works:

```bash
ollama list
```

You should see `command-r7b:latest` in the list.

---

## Step 6: Start infrastructure containers

Docman needs two services running: NATS (a message broker) and Redis (a data store).

```bash
docker run -d --name loom-nats -p 4222:4222 nats:2.10-alpine
docker run -d --name loom-redis -p 6379:6379 redis:7-alpine
```

Verify they're running:

```bash
docker ps
```

You should see two containers: `loom-nats` and `loom-redis`.

> **Note:** These containers will stop if you restart your Mac. To start them again later:
> ```bash
> docker start loom-nats loom-redis
> ```

---

## Step 7: Get the project code

Choose a directory where you want to keep the project. This example uses your home directory:

```bash
cd ~
mkdir -p Developer/IranTransitionProject
cd Developer/IranTransitionProject
```

Clone all three repositories:

```bash
git clone https://github.com/IranTransitionProject/loom.git
git clone https://github.com/IranTransitionProject/docman.git
git clone https://github.com/IranTransitionProject/framework.git
```

> **Note:** If these are private repositories, you'll need to authenticate with GitHub first. The simplest way:
> ```bash
> brew install gh
> gh auth login
> ```
> Follow the prompts to log in with your GitHub account.

---

## Step 8: Install Loom and Docman

`uv` manages virtual environments and dependencies automatically — no manual venv activation needed.

```bash
# Install Loom (the framework) with all extras
cd ~/Developer/IranTransitionProject/loom
uv sync --all-extras

# Install Docman (the test project) with dev tools
# This also resolves Loom from the sibling directory automatically
cd ~/Developer/IranTransitionProject/docman
uv sync --extra dev
```

This will download and install many packages (including PyTorch for document processing). It may take 5–10 minutes.

Verify installation:

```bash
uv run loom --help
```

You should see a list of Loom commands: `worker`, `processor`, `pipeline`, `orchestrator`, `scheduler`, `router`, `submit`, `mcp`.

---

## Step 9: Download Docling detection models

Docling uses AI models for document layout detection. Pre-download them so they're ready when you need them:

```bash
uv run docling-tools models download
```

This downloads a few hundred MB of models. They're cached at `~/.cache/docling/models/`.

---

## Step 10: Run the tests

Let's verify everything is installed correctly:

```bash
# Test Loom
cd ~/Developer/IranTransitionProject/loom
uv run pytest tests/ -v --ignore=tests/test_integration.py

# Test Docman
cd ~/Developer/IranTransitionProject/docman
uv run pytest tests/ -v
```

All tests should pass (green). The Loom integration test is excluded because it needs the full pipeline running.

---

## Step 11: Run the full pipeline

Now let's run the complete document processing pipeline.

### 11a: Set environment variables

```bash
cd ~/Developer/IranTransitionProject/docman
source .env
```

This sets `NATS_URL`, `OLLAMA_URL`, and `OLLAMA_MODEL`.

### 11b: Create a test workspace

```bash
mkdir -p /tmp/docman-workspace
```

If you have a PDF you'd like to test with, copy it there:

```bash
cp ~/Downloads/your-document.pdf /tmp/docman-workspace/
```

### 11c: Start the pipeline

```bash
./scripts/dev-start.sh
```

This starts the pipeline components in the background: router, extractor, classifier, summarizer, ingest, and pipeline orchestrator.

### 11d: Submit a test document

```bash
./scripts/dev-start.sh submit test_report.pdf
```

### 11e: Watch the logs

```bash
tail -f .dev-pids/*.log
```

Press **Ctrl + C** to stop watching logs.

### 11f: Stop the pipeline

```bash
./scripts/dev-start.sh stop
```

---

## Common tasks

### Adding a new worker

Workers are defined by YAML configuration files. To create a new one:

1. Copy an existing worker config:
   ```bash
   cp configs/workers/doc_classifier.yaml configs/workers/my_new_worker.yaml
   ```
2. Edit the file to define your worker's system prompt, input/output schemas, and behavior
3. Start it:
   ```bash
   uv run loom worker --config configs/workers/my_new_worker.yaml --tier local --nats-url nats://localhost:4222
   ```

See `loom/configs/workers/_template.yaml` for a blank template with documentation.

### Adding a new processing backend

Processing backends handle non-LLM tasks (like document extraction). To create one:

1. Create a new Python file in `docman/src/docman/backends/`
2. Implement the `ProcessingBackend` interface from Loom
3. Reference it in a worker config:
   ```yaml
   processing_backend: "docman.backends.my_backend.MyBackend"
   ```

See `docman/src/docman/backends/docling_backend.py` for an example.

### Modifying the pipeline

Pipeline stages are defined in `configs/orchestrators/doc_pipeline_local.yaml`. You can:

- Reorder stages
- Add new stages that reference your workers
- Change input mappings to pass data between stages

### Trying a different Ollama model

```bash
# See available models
ollama list

# Pull a new model
ollama pull llama3.2:3b

# Set it as the active model
export OLLAMA_MODEL=llama3.2:3b

# Restart the pipeline
./scripts/dev-start.sh stop
./scripts/dev-start.sh
```

---

## Troubleshooting

### "command not found: brew"

Run the PATH setup commands from Step 2 again, or close and reopen Terminal.

### "command not found: python3"

Make sure Homebrew's Python is installed: `brew install python@3.13`

### "command not found: loom"

Use `uv run loom` instead of bare `loom`, or activate the venv: `source .venv/bin/activate`

### NATS or Redis container not running

```bash
docker start loom-nats loom-redis
```

If they don't exist yet, re-run the `docker run` commands from Step 6.

### Ollama model fails to load

Some larger models need more RAM than your Mac has available. Stick with models 8B parameters or smaller (like `command-r7b:latest` or `llama3.2:3b`). Close memory-heavy applications if needed.

### "ModuleNotFoundError" when running tests

Make sure you ran `uv sync` in both repos (Step 8). Use `uv run pytest` to ensure the correct environment is used.

### Slow first run of document extraction

The first time Docling processes a document, it may take longer while PyTorch compiles operations for your GPU. Subsequent runs will be faster.

---

## Architecture overview

For those who want to understand how the pieces fit together:

```
You submit a document (PDF/DOCX)
        │
        ▼
┌──────────────┐     NATS message bus
│   Pipeline   │◄──────────────────────►  Coordinates the 4 stages
│ Orchestrator │
└──────┬───────┘
       │ Stage 1: extract
       ▼
┌──────────────┐
│  Extractor   │  DoclingBackend reads PDF → extracts text, tables, structure
│  (Processor) │  Writes extracted JSON to workspace
└──────┬───────┘
       │ Stage 2: classify
       ▼
┌──────────────┐
│  Classifier  │  LLM (Ollama) classifies document type from extracted text
│  (LLM Worker)│  Returns: document_type, confidence, reasoning
└──────┬───────┘
       │ Stage 3: summarize
       ▼
┌──────────────┐
│  Summarizer  │  LLM (Ollama) produces structured summary
│  (LLM Worker)│  Returns: summary, key_points, word_count
└──────┬───────┘
       │ Stage 4: ingest
       ▼
┌──────────────┐
│   Ingest     │  DuckDBIngestBackend persists all results to DuckDB
│  (Processor) │  Returns: document_id, status
└──────────────┘
```

All communication happens through NATS messages. Workers are stateless — they process one task at a time and reset. The router determines which worker handles each task based on deterministic rules (no AI involved in routing).
