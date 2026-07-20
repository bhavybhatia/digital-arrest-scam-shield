# Windows PowerShell equivalent of setup.sh
$ErrorActionPreference = "Stop"  # exit immediately if any setup command fails

$script:ChildProcesses = @()

function Stop-AllServices {
    Write-Host ""
    Write-Host "Stopping all services..."
    foreach ($proc in $script:ChildProcesses) {
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

try {
    # --- 1. System-level dependencies (needed to build pyaudio's C extension) ---
    # Not needed on Windows: PyAudio installs from a prebuilt wheel via pip,
    # so there is no portaudio dev package to install first.

    # --- 2. Python virtual environment ---
    python -m venv scam_shield_env
    .\scam_shield_env\Scripts\Activate.ps1

    # --- 3. Python dependencies (requirements.txt pins the CPU-only torch build
    #         itself via --extra-index-url, so this is the only install needed) ---
    pip install --no-cache-dir -r requirements.txt

    # --- 4. TLS certificate, shared by the backend and both Vite dev servers ---
    & "$PSScriptRoot\scripts\generate-cert.ps1"

    # --- 5. Backend (runs in background, otherwise the script hangs here forever) ---
    $backendProcess = Start-Process -FilePath "python" -ArgumentList @("app.py") -WorkingDirectory "backend" -NoNewWindow -PassThru
    $script:ChildProcesses += $backendProcess
    Write-Host "Backend started (PID $($backendProcess.Id))"

    # --- 5. Caller frontend ---
    Push-Location "frontend/caller/client"
    npm install
    $callerProcess = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") -NoNewWindow -PassThru
    Pop-Location   # back to project root
    $script:ChildProcesses += $callerProcess
    Write-Host "Caller frontend started (PID $($callerProcess.Id))"

    # --- 6. Receiver frontend ---
    Push-Location "frontend/receiver/client"
    npm install
    $receiverProcess = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") -NoNewWindow -PassThru
    Pop-Location
    $script:ChildProcesses += $receiverProcess
    Write-Host "Receiver frontend started (PID $($receiverProcess.Id))"

    Write-Host ""
    Write-Host "All services running. Press Ctrl+C to stop everything."

    # Keep the script alive so the finally block can catch Ctrl+C and clean up all 3 background processes
    Wait-Process -Id $script:ChildProcesses.Id
}
finally {
    Stop-AllServices
}
