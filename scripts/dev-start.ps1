# Docman Development Pipeline Launcher for Windows (fully local — no Anthropic API needed)
#
# Usage (from the docman directory, with venv activated):
#   .\scripts\dev-start.ps1                    # Start all pipeline components
#   .\scripts\dev-start.ps1 -Action submit     # Submit a test document
#   .\scripts\dev-start.ps1 -Action stop       # Stop all background components
#   .\scripts\dev-start.ps1 -Action status     # Check component status
#
# Prerequisites:
#   - Docker Desktop running (NATS + Redis containers)
#   - Ollama running with a model (default: command-r7b:latest)
#   - Python venv activated

param(
    [ValidateSet("start", "submit", "stop", "status")]
    [string]$Action = "start",

    [string]$File = "test_report.pdf"
)

$ErrorActionPreference = "Stop"

# Paths
$DocmanDir = Split-Path -Parent $PSScriptRoot
$LoomDir = Join-Path (Split-Path -Parent $DocmanDir) "loom"
$Workspace = "C:\temp\docman-workspace"
$PidDir = Join-Path $DocmanDir ".dev-pids"

# Environment defaults
if (-not $env:NATS_URL)     { $env:NATS_URL = "nats://localhost:4222" }
if (-not $env:OLLAMA_URL)   { $env:OLLAMA_URL = "http://localhost:11434" }
if (-not $env:OLLAMA_MODEL) { $env:OLLAMA_MODEL = "command-r7b:latest" }

function Write-Status($msg)  { Write-Host "[docman] $msg" -ForegroundColor Green }
function Write-Warn($msg)    { Write-Host "[docman] $msg" -ForegroundColor Yellow }
function Write-Err($msg)     { Write-Host "[docman] $msg" -ForegroundColor Red }

function Test-Prerequisites {
    # Check Docker / NATS
    $containers = docker ps --format "{{.Names}}" 2>$null
    if ($containers -notmatch "nats") {
        Write-Err "NATS container not running. Start with:"
        Write-Err "  docker run -d --name loom-nats -p 4222:4222 nats:2.10-alpine"
        exit 1
    }
    Write-Status "NATS: running"

    # Check Ollama
    try {
        $null = Invoke-RestMethod -Uri "$env:OLLAMA_URL/api/tags" -TimeoutSec 5
        Write-Status "Ollama: running (model: $env:OLLAMA_MODEL)"
    } catch {
        Write-Err "Ollama not responding at $env:OLLAMA_URL"
        exit 1
    }

    # Check venv
    if (-not $env:VIRTUAL_ENV) {
        Write-Warn "No virtualenv active. Activate with: .venv\Scripts\Activate.ps1"
    }

    # Create directories
    if (-not (Test-Path $Workspace)) { New-Item -ItemType Directory -Path $Workspace -Force | Out-Null }
    if (-not (Test-Path $PidDir))    { New-Item -ItemType Directory -Path $PidDir -Force | Out-Null }
    Write-Status "Workspace: $Workspace"
}

function Start-Component {
    param([string]$Name, [string]$Command, [string[]]$Arguments)

    $logFile = Join-Path $PidDir "$Name.log"
    Write-Status "Starting $Name..."

    $proc = Start-Process -FilePath $Command -ArgumentList $Arguments `
        -RedirectStandardOutput $logFile -RedirectStandardError (Join-Path $PidDir "$Name.err.log") `
        -NoNewWindow -PassThru

    $proc.Id | Out-File -FilePath (Join-Path $PidDir "$Name.pid") -NoNewline
    Write-Status "  $Name started (PID: $($proc.Id), log: $logFile)"
}

function Invoke-Start {
    Test-Prerequisites

    # Pre-warm the Ollama model
    Write-Status "Pre-warming Ollama model: $env:OLLAMA_MODEL..."
    try {
        $body = @{ model = $env:OLLAMA_MODEL; prompt = "hello"; stream = $false } | ConvertTo-Json
        $null = Invoke-RestMethod -Uri "$env:OLLAMA_URL/api/generate" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 120
    } catch {
        Write-Warn "Model pre-warm returned an error (may still work): $_"
    }

    Push-Location $DocmanDir

    # 1. Router
    Start-Component -Name "router" -Command "loom" -Arguments @(
        "router",
        "--config", (Join-Path $LoomDir "configs\router_rules.yaml"),
        "--nats-url", $env:NATS_URL
    )
    Start-Sleep -Seconds 2

    # 2. Doc Extractor (processor worker with DoclingBackend)
    Start-Component -Name "extractor" -Command "loom" -Arguments @(
        "processor",
        "--config", "configs\workers\doc_extractor_windows.yaml",
        "--nats-url", $env:NATS_URL
    )

    # 3. Doc Classifier (LLM worker — local tier via Ollama)
    Start-Component -Name "classifier" -Command "loom" -Arguments @(
        "worker",
        "--config", "configs\workers\doc_classifier.yaml",
        "--tier", "local",
        "--nats-url", $env:NATS_URL
    )

    # 4. Doc Summarizer (LLM worker — local tier via Ollama)
    Start-Component -Name "summarizer" -Command "loom" -Arguments @(
        "worker",
        "--config", "configs\workers\doc_summarizer_local.yaml",
        "--tier", "local",
        "--nats-url", $env:NATS_URL
    )

    # 5. Pipeline Orchestrator
    Start-Component -Name "pipeline" -Command "loom" -Arguments @(
        "pipeline",
        "--config", "configs\orchestrators\doc_pipeline_local.yaml",
        "--nats-url", $env:NATS_URL
    )

    Pop-Location

    Start-Sleep -Seconds 2
    Write-Status ""
    Write-Status "All components started. Submit a test with:"
    Write-Status "  .\scripts\dev-start.ps1 -Action submit"
    Write-Status ""
    Write-Status "View logs:"
    Write-Status "  Get-Content .dev-pids\*.log -Tail 20 -Wait"
    Write-Status ""
    Write-Status "Stop all:"
    Write-Status "  .\scripts\dev-start.ps1 -Action stop"
}

function Invoke-Submit {
    Write-Status "Submitting document: $File"
    loom submit "Process document" --context "file_ref=$File" --nats-url $env:NATS_URL
}

function Invoke-Stop {
    Write-Status "Stopping all dev components..."
    Get-ChildItem -Path $PidDir -Filter "*.pid" -ErrorAction SilentlyContinue | ForEach-Object {
        $name = $_.BaseName
        $pid = Get-Content $_.FullName
        try {
            $proc = Get-Process -Id $pid -ErrorAction Stop
            Stop-Process -Id $pid -Force
            Write-Status "  Stopped $name (PID: $pid)"
        } catch {
            Write-Status "  $name already stopped"
        }
        Remove-Item $_.FullName -Force
    }
    Write-Status "All components stopped."
}

function Invoke-Status {
    Write-Status "Component status:"
    Get-ChildItem -Path $PidDir -Filter "*.pid" -ErrorAction SilentlyContinue | ForEach-Object {
        $name = $_.BaseName
        $pid = Get-Content $_.FullName
        try {
            $null = Get-Process -Id $pid -ErrorAction Stop
            Write-Host "  * $name (PID: $pid) - running" -ForegroundColor Green
        } catch {
            Write-Host "  * $name (PID: $pid) - not running" -ForegroundColor Red
        }
    }
}

# Main
switch ($Action) {
    "start"  { Invoke-Start }
    "submit" { Invoke-Submit }
    "stop"   { Invoke-Stop }
    "status" { Invoke-Status }
}
