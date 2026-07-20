##!/bin/bash
#set -e  # exit immediately if any setup command fails
#
## Kill all background processes started by this script when it exits (Ctrl+C, etc.)
#trap 'echo ""; echo "Stopping all services..."; kill $(jobs -p) 2>/dev/null' EXIT INT TERM
#
## --- 1. System-level dependencies (needed to build pyaudio's C extension) ---
##sudo apt update
##sudo apt install -y portaudio19-dev python3-dev
#
## --- 2. Python virtual environment ---
#python3 -m venv scam_shield_env
#source scam_shield_env/bin/activate
#
## --- 3. Python dependencies (CPU-only torch first, so pip never pulls the ~2GB CUDA build) ---
#pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
#pip install --no-cache-dir -r requirements.txt
#
## --- 4. TLS certificate, shared by the backend and both Vite dev servers ---
#bash scripts/generate-cert.sh
#
## --- 5. Backend (runs in background, otherwise the script hangs here forever) ---
#cd backend
#python app.py &
#BACKEND_PID=$!
#cd ..
#echo "Backend started (PID $BACKEND_PID)"
#
## --- 5. Caller frontend ---
#cd frontend/caller/client
#npm install
#npm run dev &
#CALLER_PID=$!
#cd ../../..   # back to project root: client -> caller -> frontend -> root
#echo "Caller frontend started (PID $CALLER_PID)"
#
## --- 6. Receiver frontend ---
#cd frontend/receiver/client
#npm install
#npm run dev &
#RECEIVER_PID=$!
#cd ../../..
#echo "Receiver frontend started (PID $RECEIVER_PID)"
#
#echo ""
#echo "All services running. Press Ctrl+C to stop everything."
#
## Keep the script alive so the trap can catch Ctrl+C and clean up all 3 background processes
#wait

#!/bin/bash
set -e  # exit immediately if any setup command fails

# Kill all background processes started by this script when it exits (Ctrl+C, etc.)
trap 'echo ""; echo "Stopping all services..."; kill $(jobs -p) 2>/dev/null' EXIT INT TERM

# =====================================================================
# 0. Detect platform
#    Linux            -> uname -s == "Linux"
#    macOS            -> uname -s == "Darwin"
#    Windows Git Bash  -> uname -s starts with "MINGW" / "MSYS"
#    Windows WSL       -> reports as "Linux" (handled by the linux branch)
#    NOTE: this script needs a bash-compatible shell. On plain Windows
#    (no Git Bash / no WSL), use the companion setup.ps1 instead.
# =====================================================================
OS_RAW="$(uname -s 2>/dev/null || echo unknown)"
case "$OS_RAW" in
  Linux*)                 PLATFORM="linux" ;;
  Darwin*)                PLATFORM="mac" ;;
  CYGWIN*|MINGW*|MSYS*)   PLATFORM="windows" ;;
  *)                      PLATFORM="unknown" ;;
esac
echo "==> Detected platform: $PLATFORM ($OS_RAW)"

# =====================================================================
# Helpers
# =====================================================================

# Resolve whichever of python3/python is actually on PATH.
resolve_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
  elif command -v python >/dev/null 2>&1; then
    echo "python"
  else
    echo ""
  fi
}

# Major version of node on PATH, or 0 if not installed.
node_major_version() {
  if command -v node >/dev/null 2>&1; then
    node -v | sed 's/^v//' | cut -d. -f1
  else
    echo 0
  fi
}

PYTHON_CMD="$(resolve_python)"
if [ -z "$PYTHON_CMD" ]; then
  echo "ERROR: no python3/python found on PATH."
  echo "Install Python 3.11+ first: https://www.python.org/downloads/"
  exit 1
fi
echo "Using Python: $("$PYTHON_CMD" --version)"

# =====================================================================
# 1. System-level dependencies (needed to build pyaudio's C extension,
#    and to make sure Node.js is new enough for Vite - requires >=18)
# =====================================================================

install_system_deps_linux() {
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "WARNING: apt-get not found (non-Debian distro?)."
    echo "Install portaudio dev headers, python3-venv/python3-dev, build tools"
    echo "and Node.js 18+ manually using your distro's package manager, then re-run."
    return
  fi

  echo "==> [Linux] Installing system packages via apt (requires sudo)..."
  sudo apt update
  sudo apt install -y portaudio19-dev python3-dev python3-venv build-essential curl

  NODE_MAJOR="$(node_major_version)"
  if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "==> Node.js missing or older than v18 (found v$NODE_MAJOR) - installing Node.js 20.x via NodeSource..."
    # apt's default 'nodejs' package is usually too old for Vite (needs >=18),
    # so pull a current LTS from NodeSource instead of the distro repo.
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
  else
    echo "Node.js v$NODE_MAJOR already satisfies requirement (>=18)."
  fi
}

install_system_deps_mac() {
  echo "==> [macOS] Checking dependencies (no sudo needed)..."
  if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: Homebrew not found. Install it first: https://brew.sh"
    echo "Then re-run this script."
    exit 1
  fi

  brew list portaudio >/dev/null 2>&1 || brew install portaudio

  NODE_MAJOR="$(node_major_version)"
  if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "==> Node.js missing or older than v18 (found v$NODE_MAJOR) - installing via Homebrew..."
    brew install node@20
    brew link --overwrite --force node@20
  else
    echo "Node.js v$NODE_MAJOR already satisfies requirement (>=18)."
  fi
}

install_system_deps_windows() {
  echo "==> [Windows/Git Bash] No apt/sudo on Windows - checking tools on PATH instead."
  echo "    (pyaudio ships a prebuilt wheel for Windows, so no compiler/portaudio-dev needed.)"

  MISSING=0
  command -v "$PYTHON_CMD" >/dev/null 2>&1 || { echo "  - Python not found."; MISSING=1; }

  NODE_MAJOR="$(node_major_version)"
  if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "  - Node.js missing or older than v18 (found v$NODE_MAJOR)."
    if command -v winget >/dev/null 2>&1; then
      echo "==> Attempting Node.js LTS install via winget..."
      winget install --id OpenJS.NodeJS.LTS -e --silent || MISSING=1
      echo "    If this just installed Node for the first time, close and reopen"
      echo "    your terminal (PATH needs to refresh), then re-run this script."
    else
      MISSING=1
    fi
  else
    echo "Node.js v$NODE_MAJOR already satisfies requirement (>=18)."
  fi

  if [ "$MISSING" -eq 1 ]; then
    echo ""
    echo "Please install the missing tool(s) manually, then re-run this script:"
    echo "  - Python 3.11+ : https://www.python.org/downloads/  (tick 'Add python.exe to PATH')"
    echo "  - Node.js 18+ LTS : https://nodejs.org/"
    exit 1
  fi
}

case "$PLATFORM" in
  linux)   install_system_deps_linux ;;
  mac)     install_system_deps_mac ;;
  windows) install_system_deps_windows ;;
  *)       echo "WARNING: unrecognized platform '$OS_RAW' - skipping system dependency install, continuing anyway." ;;
esac

# =====================================================================
# 2. Python virtual environment
#    Windows' venv module creates 'Scripts/activate' instead of 'bin/activate'.
# =====================================================================
echo "==> Creating Python virtual environment..."
"$PYTHON_CMD" -m venv scam_shield_env

if [ "$PLATFORM" = "windows" ]; then
  VENV_ACTIVATE="scam_shield_env/Scripts/activate"
else
  VENV_ACTIVATE="scam_shield_env/bin/activate"
fi
source "$VENV_ACTIVATE"
echo "Virtual environment activated ($VENV_ACTIVATE)"

# Once the venv is active, 'python' and 'pip' resolve to the venv's own
# interpreter on every platform - no more python/python3 branching needed.
PY="python"

# =====================================================================
# 3. Python dependencies (CPU-only torch first, so pip never pulls the
#    ~2GB CUDA build)
# =====================================================================
echo "==> Installing Python dependencies..."
$PY -m pip install --upgrade pip
pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
pip install --no-cache-dir -r requirements.txt

# --- 3.1 TLS certificate, shared by the backend and both Vite dev servers ---
bash scripts/generate-cert.sh

# =====================================================================
# 4. Backend (runs in background, otherwise the script hangs here forever)
# =====================================================================
cd backend
$PY app.py &
BACKEND_PID=$!
cd ..
echo "Backend started (PID $BACKEND_PID)"

# =====================================================================
# 5. Caller frontend
# =====================================================================
cd frontend/caller/client
npm install
npm run dev &
CALLER_PID=$!
cd ../../..   # back to project root: client -> caller -> frontend -> root
echo "Caller frontend started (PID $CALLER_PID)"

# =====================================================================
# 6. Receiver frontend
# =====================================================================
cd frontend/receiver/client
npm install
npm run dev &
RECEIVER_PID=$!
cd ../../..
echo "Receiver frontend started (PID $RECEIVER_PID)"

echo ""
echo "All services running on platform: $PLATFORM"
echo "Press Ctrl+C to stop everything."

# Keep the script alive so the trap can catch Ctrl+C and clean up all 3 background processes
wait