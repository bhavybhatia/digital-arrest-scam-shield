#!/bin/bash
set -e  # exit immediately if any setup command fails

# Kill all background processes started by this script when it exits (Ctrl+C, etc.)
trap 'echo ""; echo "Stopping all services..."; kill $(jobs -p) 2>/dev/null' EXIT INT TERM

# --- 1. Python virtual environment ---
# python3 -m venv scam_shield_env
# source scam_shield_env/bin/activate

# pip install -r requirements.txt

# --- 2. Backend (runs in background, otherwise the script hangs here forever) ---
cd backend
python3 app.py &
BACKEND_PID=$!
cd ..
echo "Backend started (PID $BACKEND_PID)"

# --- 3. Caller frontend ---
cd frontend/caller/client
npm install
npm run dev &
CALLER_PID=$!
cd ../../..   # back to project root: client -> caller -> frontend -> root
echo "Caller frontend started (PID $CALLER_PID)"

# --- 4. Receiver frontend ---
cd frontend/receiver/client
npm install
npm run dev &
RECEIVER_PID=$!
cd ../../..
echo "Receiver frontend started (PID $RECEIVER_PID)"

echo ""
echo "All services running. Press Ctrl+C to stop everything."

# Keep the script alive so the trap can catch Ctrl+C and clean up all 3 background processes
wait