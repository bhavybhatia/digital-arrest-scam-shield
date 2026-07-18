# =====================================================================
# setup.ps1 - Native Windows setup (PowerShell, no Git Bash / WSL needed)
#
# Run from an ordinary PowerShell prompt in the project root:
#     .\setup.ps1
# If script execution is blocked, run once per session:
#     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# =====================================================================

$ErrorActionPreference = "Stop"
Write-Host "==> Platform: Windows (PowerShell)"

# ---------------------------------------------------------------------
# Helper: resolve python / py launcher
# ---------------------------------------------------------------------
function Resolve-Python {
    if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
    if (Get-Command py -ErrorAction SilentlyContinue) { return "py" }
    return $null
}

$PythonCmd = Resolve-Python
if (-not $PythonCmd) {
    Write-Host "ERROR: Python not found on PATH."
    Write-Host "Install Python 3.11+ from https://www.python.org/downloads/"
    Write-Host "(tick 'Add python.exe to PATH' during install), then re-run this script."
    exit 1
}
Write-Host "Using Python: $(& $PythonCmd --version)"

# ---------------------------------------------------------------------
# Helper: Node.js version check (Vite needs >= 18)
# ---------------------------------------------------------------------
function Get-NodeMajorVersion {
    if (Get-Command node -ErrorAction SilentlyContinue) {
        $v = (node -v) -replace '^v', ''
        return [int]($v.Split('.')[0])
    }
    return 0
}

$nodeMajor = Get-NodeMajorVersion
if ($nodeMajor -lt 18) {
    Write-Host "Node.js missing or older than v18 (found v$nodeMajor)."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "==> Installing Node.js LTS via winget..."
        winget install --id OpenJS.NodeJS.LTS -e --silent
        Write-Host ""
        Write-Host "Node.js was just installed. Close this window, open a NEW PowerShell"
        Write-Host "prompt (so PATH refreshes), and re-run: .\setup.ps1"
        exit 0
    } else {
        Write-Host "winget not available. Install Node.js 18+ LTS manually: https://nodejs.org/"
        exit 1
    }
} else {
    Write-Host "Node.js v$nodeMajor OK (>= 18 required)"
}

# No sudo / apt equivalent needed on Windows:
# pyaudio ships a prebuilt wheel for Windows, so no compiler or portaudio
# dev headers are required the way they are on Linux.

# ---------------------------------------------------------------------
# Python virtual environment
# ---------------------------------------------------------------------
Write-Host "==> Creating Python virtual environment..."
& $PythonCmd -m venv scam_shield_env
& .\scam_shield_env\Scripts\Activate.ps1
Write-Host "Virtual environment activated."

# ---------------------------------------------------------------------
# Python dependencies (CPU-only torch first, so pip never pulls the
# ~2GB CUDA build)
# ---------------------------------------------------------------------
Write-Host "==> Installing Python dependencies..."
python -m pip install --upgrade pip
pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------
# Launch backend + both frontends as background processes
# ---------------------------------------------------------------------
Write-Host "==> Starting backend..."
$backend = Start-Process -FilePath "python" -ArgumentList "app.py" `
    -WorkingDirectory "backend" -PassThru -NoNewWindow
Write-Host "Backend started (PID $($backend.Id))"

Write-Host "==> Starting caller frontend..."
Push-Location "frontend/caller/client"
npm install
$caller = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" -PassThru -NoNewWindow
Pop-Location
Write-Host "Caller frontend started (PID $($caller.Id))"

Write-Host "==> Starting receiver frontend..."
Push-Location "frontend/receiver/client"
npm install
$receiver = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" -PassThru -NoNewWindow
Pop-Location
Write-Host "Receiver frontend started (PID $($receiver.Id))"

Write-Host ""
Write-Host "All services running. Press Ctrl+C to stop everything."

# ---------------------------------------------------------------------
# Keep the script alive; clean up all 3 processes on Ctrl+C / exit
# ---------------------------------------------------------------------
try {
    Wait-Process -Id $backend.Id, $caller.Id, $receiver.Id
}
finally {
    Write-Host ""
    Write-Host "Stopping all services..."
    Stop-Process -Id $backend.Id, $caller.Id, $receiver.Id -ErrorAction SilentlyContinue
}
