#!/usr/bin/env bash
# Docman Development Pipeline Launcher (fully local — no Anthropic API needed)
#
# Usage:
#   ./scripts/dev-start.sh          # Start all pipeline components
#   ./scripts/dev-start.sh submit   # Submit a test document
#   ./scripts/dev-start.sh stop     # Stop all background components
#
# Prerequisites:
#   - OrbStack / Docker running (NATS + Redis containers)
#   - Ollama running with a model (default: gemma3:27b)
#   - Python venv activated: source ../.venv/bin/activate

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCMAN_DIR="$(dirname "$SCRIPT_DIR")"
LOOM_DIR="$(dirname "$DOCMAN_DIR")/loom"
WORKSPACE="/tmp/docman-workspace"
PID_DIR="$DOCMAN_DIR/.dev-pids"

# Environment
export NATS_URL="${NATS_URL:-nats://localhost:4222}"
export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-command-r7b:latest}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[docman]${NC} $*"; }
warn() { echo -e "${YELLOW}[docman]${NC} $*"; }
err()  { echo -e "${RED}[docman]${NC} $*" >&2; }

check_prereqs() {
    # Check NATS
    if ! docker ps --format '{{.Names}}' | grep -q nats; then
        err "NATS container not running. Start with:"
        err "  docker run -d --name loom-nats -p 4222:4222 nats:2.10-alpine"
        exit 1
    fi
    log "NATS: running"

    # Check Ollama
    if ! curl -s "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
        err "Ollama not responding at $OLLAMA_URL"
        exit 1
    fi
    log "Ollama: running (model: $OLLAMA_MODEL)"

    # Check venv
    if [ -z "${VIRTUAL_ENV:-}" ]; then
        warn "No virtualenv active. Activate with: source ../.venv/bin/activate"
    fi

    # Create workspace
    mkdir -p "$WORKSPACE"
    mkdir -p "$PID_DIR"
    log "Workspace: $WORKSPACE"
}

start_component() {
    local name="$1"
    shift
    local logfile="$PID_DIR/${name}.log"

    log "Starting ${BLUE}${name}${NC}..."
    "$@" > "$logfile" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_DIR/${name}.pid"
    log "  ${name} started (PID: $pid, log: $logfile)"
}

cmd_start() {
    check_prereqs

    # Pre-warm the Ollama model
    log "Pre-warming Ollama model: $OLLAMA_MODEL..."
    curl -s "$OLLAMA_URL/api/generate" -d "{\"model\": \"$OLLAMA_MODEL\", \"prompt\": \"hello\", \"stream\": false}" > /dev/null 2>&1 &

    cd "$DOCMAN_DIR"

    # 1. Router
    start_component "router" \
        loom router \
            --config "$LOOM_DIR/configs/router_rules.yaml" \
            --nats-url "$NATS_URL"

    sleep 1

    # 2. Doc Extractor (processor worker with DoclingBackend)
    start_component "extractor" \
        loom processor \
            --config configs/workers/doc_extractor.yaml \
            --nats-url "$NATS_URL"

    # 3. Doc Classifier (LLM worker — local tier via Ollama)
    start_component "classifier" \
        loom worker \
            --config configs/workers/doc_classifier.yaml \
            --tier local \
            --nats-url "$NATS_URL"

    # 4. Doc Summarizer (LLM worker — local tier via Ollama)
    start_component "summarizer" \
        loom worker \
            --config configs/workers/doc_summarizer_local.yaml \
            --tier local \
            --nats-url "$NATS_URL"

    # 5. Pipeline Orchestrator
    start_component "pipeline" \
        loom pipeline \
            --config configs/orchestrators/doc_pipeline_local.yaml \
            --nats-url "$NATS_URL"

    sleep 2
    log ""
    log "All components started. Submit a test with:"
    log "  ./scripts/dev-start.sh submit"
    log ""
    log "View logs:"
    log "  tail -f $PID_DIR/*.log"
    log ""
    log "Stop all:"
    log "  ./scripts/dev-start.sh stop"
}

cmd_submit() {
    local file="${1:-test_report.pdf}"
    log "Submitting document: $file"
    loom submit "Process document" \
        --context "file_ref=$file" \
        --nats-url "$NATS_URL"
}

cmd_stop() {
    log "Stopping all dev components..."
    for pidfile in "$PID_DIR"/*.pid; do
        [ -f "$pidfile" ] || continue
        local name
        name="$(basename "$pidfile" .pid)"
        local pid
        pid="$(cat "$pidfile")"
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            log "  Stopped $name (PID: $pid)"
        else
            log "  $name already stopped"
        fi
        rm -f "$pidfile"
    done
    log "All components stopped."
}

cmd_status() {
    log "Component status:"
    for pidfile in "$PID_DIR"/*.pid; do
        [ -f "$pidfile" ] || continue
        local name
        name="$(basename "$pidfile" .pid)"
        local pid
        pid="$(cat "$pidfile")"
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "  ${GREEN}●${NC} $name (PID: $pid)"
        else
            echo -e "  ${RED}●${NC} $name (PID: $pid — not running)"
        fi
    done
}

# Main
case "${1:-start}" in
    start)  cmd_start ;;
    submit) shift; cmd_submit "$@" ;;
    stop)   cmd_stop ;;
    status) cmd_status ;;
    *)      echo "Usage: $0 {start|submit [file]|stop|status}"; exit 1 ;;
esac
