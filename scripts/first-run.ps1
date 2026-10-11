# PowerShell First-Run Automation for Lenny Growth Assistant
# Builds containers, waits for health, fetches data, and ingests transcripts.

$ErrorActionPreference = "Stop"

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "  Lenny Growth Assistant - First-Run Initializer       " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

# 1. Environment configuration
if (-not (Test-Path ".env")) {
    Write-Host "[1/5] Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
} else {
    Write-Host "[1/5] Using existing .env configuration." -ForegroundColor Green
}

# 2. Fetch transcript data
Write-Host "[2/5] Fetching podcast transcripts..." -ForegroundColor Yellow
$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $py scripts/fetch_data.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to fetch transcripts repository. Please check network connection."
    exit 1
}

# 3. Build and launch Docker containers
Write-Host "[3/5] Building and launching Docker Compose containers..." -ForegroundColor Yellow
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker compose build failed."
    exit 1
}

# 4. Wait until backend is healthy
Write-Host "[4/5] Waiting for backend to become healthy..." -ForegroundColor Yellow
$healthy = $false
$maxAttempts = 30
for ($i = 1; $i -le $maxAttempts; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 3 -ErrorAction SilentlyContinue
        if ($resp -and $resp.database -and $resp.database.connected -eq $true) {
            $healthy = $true
            Write-Host "Backend reported healthy (DB connected)!" -ForegroundColor Green
            break
        }
    } catch {
        # Waiting for container and uvicorn startup
    }
    Start-Sleep -Seconds 2
}

if (-not $healthy) {
    Write-Error "Backend did not become healthy within 60 seconds."
    exit 1
}

# 5. Ingest transcripts into pgvector
Write-Host "[5/5] Ingesting transcripts into pgvector..." -ForegroundColor Yellow
docker compose exec -T backend python -m scripts.ingest
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Ingestion completed with errors or warnings. Check Ollama reachability."
}

Write-Host ""
Write-Host "======================================================" -ForegroundColor Green
Write-Host "  Lenny Growth Assistant is Ready!                     " -ForegroundColor Green
Write-Host "  Frontend : http://localhost:3000                     " -ForegroundColor Green
Write-Host "  Backend  : http://localhost:8000                     " -ForegroundColor Green
Write-Host "  API Docs : http://localhost:8000/docs                " -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green
