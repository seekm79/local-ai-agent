# dev.ps1 — Windows equivalent of `make dev`.
# Starts the FastAPI backend (:8010) and the Vite frontend (:5173) together,
# each in its own window, and streams their output. Ctrl+C in this window
# stops both child processes.
#
# Usage:   ./dev.ps1
# First-time setup is documented in README.md.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# --- Resolve the backend Python (prefer the venv, fall back to the launcher) --
$venvPy = Join-Path $root "backend\.venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $backendPy = $venvPy
} else {
    Write-Warning "backend\.venv not found — using 'py'. Run setup (see README) for an isolated env."
    $backendPy = "py"
}

Write-Host "Starting backend on http://127.0.0.1:8010 ..." -ForegroundColor Cyan
# NOTE: no --reload on Windows. uvicorn >=0.50 builds the event loop from a
# factory that returns a SelectorEventLoop whenever the server runs under a
# subprocess (which --reload forces). The Selector loop cannot spawn asyncio
# subprocesses, so the project runner (Build-tab installs, dev servers, agent
# tools) dies with NotImplementedError. Without --reload uvicorn uses the
# ProactorEventLoop, which supports subprocesses. Frontend HMR still gives
# instant UI reloads; restart this script after backend code changes.
$backend = Start-Process -PassThru -NoNewWindow -WorkingDirectory (Join-Path $root "backend") `
    -FilePath $backendPy -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8010")

Write-Host "Starting frontend on http://127.0.0.1:5173 ..." -ForegroundColor Cyan
$frontend = Start-Process -PassThru -NoNewWindow -WorkingDirectory (Join-Path $root "frontend") `
    -FilePath "npm" -ArgumentList @("run", "dev")

Write-Host ""
Write-Host "Both servers starting. Open http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow

try {
    Wait-Process -Id $backend.Id, $frontend.Id
} finally {
    foreach ($p in @($backend, $frontend)) {
        if ($p -and -not $p.HasExited) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
    Write-Host "Stopped." -ForegroundColor Yellow
}
