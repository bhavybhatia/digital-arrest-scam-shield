"""
Backend for the Digital-Arrest Scam Call Simulator.

This is the ONLY place business logic lives:
  - call session state machine (idle -> ringing -> active -> ended/rejected)
  - kicking off realtime_transcribe.py's recorder/transcriber threads
  - running every transcript chunk through digital_scam_shield.py
  - persisting the transcript to transcription.docx

Both React screens (caller_ui, receiver_ui) are thin polling clients of
this API. They contain no state-machine logic, no scoring logic, and no
knowledge of Whisper / ModernBERT.
"""

import os
import sys
import threading
import uuid
from datetime import datetime

from flask import Flask, jsonify, request
from flask_cors import CORS

# Windows consoles default to a codepage (e.g. cp1252) that can't encode the
# arrow/emoji characters digital_scam_shield.py prints (e.g. "►", "🔴"). An
# unhandled UnicodeEncodeError there would otherwise kill the transcriber
# thread the first time a chunk gets scored, silently stopping all further
# transcription for the call.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from realtime_transcribe import (  # noqa: E402
    init_doc,
    record_audio,
    transcribe_audio,
    audio_queue,
    stop_event,
    mark_call_event,
    OUTPUT_PATH,
)
from digital_scam_shield import scam_detector, preload as preload_scam_model  # noqa: E402

import whisper  # noqa: E402

app = Flask(__name__)
# caller/client (Vite dev, port 5173) and receiver/client (Vite dev, port
# 5174) call this API directly — there is no Node proxy layer in between.
CORS(app, origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
])

# ---------------------------------------------------------------------------
# Model loading (once, at startup, before any audio thread starts — loading
# concurrently with an active PyAudio stream has been observed to crash).
# ---------------------------------------------------------------------------
print("Loading Whisper model (tiny)...")
whisper_model = whisper.load_model("tiny")
print("Whisper model loaded.")

print("Preloading scam-analyser (HF Router LLM)...")
preload_scam_model()
print("Scam analyser ready.\n")

init_doc()

# ---------------------------------------------------------------------------
# In-memory state (single active call at a time — this is a simulator)
# ---------------------------------------------------------------------------
state_lock = threading.Lock()
log_lock = threading.Lock()
session_lock = threading.Lock()

recorder_thread = None
transcriber_thread = None
is_recording = False
transcript_log = []  # [{index, timestamp, text, scam_score, scam_label, risk_status}]

session = {
    "session_id": None,
    "from_number": None,
    "to_number": None,
    "status": "idle",  # idle | ringing | active | ended | rejected
    "started_at": None,
    "accepted_at": None,
    "ended_at": None,
}


def _on_chunk(timestamp, text):
    """Callback invoked by transcribe_audio() for every finished chunk."""
    score, top_label, risk_status = scam_detector(text)
    with log_lock:
        transcript_log.append({
            "index": len(transcript_log),
            "timestamp": timestamp,
            "text": text,
            "scam_score": score,
            "scam_label": top_label,
            "risk_status": risk_status,
        })


def _start_recording():
    global recorder_thread, transcriber_thread, is_recording
    with state_lock:
        if is_recording:
            return
        stop_event.clear()
        while not audio_queue.empty():
            audio_queue.get_nowait()

        recorder_thread = threading.Thread(target=record_audio, daemon=True)
        transcriber_thread = threading.Thread(
            target=transcribe_audio,
            args=(whisper_model,),
            kwargs={"on_chunk": _on_chunk},
            daemon=True,
        )
        recorder_thread.start()
        transcriber_thread.start()
        is_recording = True

    mark_call_event("Recording started")


def _stop_recording():
    global is_recording
    with state_lock:
        if not is_recording:
            return
        stop_event.set()
        if recorder_thread:
            recorder_thread.join(timeout=10)
        if transcriber_thread:
            transcriber_thread.join(timeout=30)
        is_recording = False

    mark_call_event("Recording stopped")


def _reset_session_locked():
    session.update({
        "session_id": None,
        "from_number": None,
        "to_number": None,
        "status": "idle",
        "started_at": None,
        "accepted_at": None,
        "ended_at": None,
    })


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return jsonify({
        "service": "digital-arrest call simulator API",
        "endpoints": {
            "POST /api/call/dial": "caller_ui places a call to a number",
            "POST /api/call/accept": "receiver_ui accepts the ringing call",
            "POST /api/call/decline": "receiver_ui declines the ringing call",
            "POST /api/call/hangup": "either side ends an active call",
            "POST /api/call/reset": "clear a finished call back to idle",
            "GET /api/call/session": "poll current call session state",
            "GET /api/call/transcript?since=<n>": "poll transcript + scam risk",
        },
    })


@app.post("/api/call/dial")
def dial():
    data = request.get_json(force=True) or {}
    to_number = (data.get("to_number") or "").strip()
    from_number = (data.get("from_number") or "Unknown").strip()

    if not to_number:
        return jsonify({"error": "to_number is required"}), 400

    with session_lock:
        if session["status"] in ("ringing", "active"):
            return jsonify({"error": "a call is already in progress"}), 409

        with log_lock:
            transcript_log.clear()

        session.update({
            "session_id": str(uuid.uuid4()),
            "from_number": from_number,
            "to_number": to_number,
            "status": "ringing",
            "started_at": datetime.now().isoformat(),
            "accepted_at": None,
            "ended_at": None,
        })
        current = dict(session)

    return jsonify(current)


@app.post("/api/call/accept")
def accept():
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id")

    with session_lock:
        if session["session_id"] != session_id or session["status"] != "ringing":
            return jsonify({"error": "no matching ringing call"}), 409
        session["status"] = "active"
        session["accepted_at"] = datetime.now().isoformat()
        current = dict(session)

    _start_recording()
    return jsonify(current)


@app.post("/api/call/decline")
def decline():
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id")

    with session_lock:
        if session["session_id"] != session_id:
            return jsonify({"error": "no matching call"}), 409
        session["status"] = "rejected"
        session["ended_at"] = datetime.now().isoformat()
        current = dict(session)

    # Defensive: a decline should never find recording active (only accept()
    # starts it), but stop it if it somehow is rather than leaving an
    # orphaned recorder/transcriber thread running into the next call.
    _stop_recording()

    return jsonify(current)


@app.post("/api/call/hangup")
def hangup():
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id")

    with session_lock:
        if session["session_id"] != session_id:
            return jsonify({"error": "no matching call"}), 409
        was_active = session["status"] == "active"
        session["status"] = "ended"
        session["ended_at"] = datetime.now().isoformat()
        current = dict(session)

    if was_active:
        _stop_recording()

    return jsonify(current)


@app.post("/api/call/reset")
def reset():
    # Defensive: guarantee no recording ever survives past a reset, even if
    # the call ended via a path other than hangup() - otherwise the old
    # recorder/transcriber threads keep running and silently attribute their
    # audio to whatever the next call turns out to be.
    _stop_recording()

    with session_lock:
        _reset_session_locked()
        current = dict(session)
    return jsonify(current)


@app.get("/api/call/session")
def get_session():
    with session_lock:
        current = dict(session)
    return jsonify(current)


@app.get("/api/call/transcript")
def get_transcript():
    since = request.args.get("since", default=0, type=int)
    with log_lock:
        chunks = transcript_log[since:]
        total = len(transcript_log)
        if transcript_log:
            latest_score = transcript_log[-1]["scam_score"]
            latest_label = transcript_log[-1]["scam_label"]
            latest_risk = transcript_log[-1]["risk_status"]
        else:
            latest_score, latest_label, latest_risk = 0, None, "\U0001F7E2 LOW RISK"

    return jsonify({
        "chunks": chunks,
        "total": total,
        "latest_score": latest_score,
        "latest_label": latest_label,
        "latest_risk": latest_risk,
        "saved_to": OUTPUT_PATH,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, threaded=True)
