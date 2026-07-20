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
import re
import os
import sys
import threading
import uuid
from datetime import datetime

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sock import Sock
from simple_websocket import ConnectionClosed

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
    transcribe_audio,
    audio_queue,
    stop_event,
    mark_call_event,
    ChunkAssembler,
    OUTPUT_PATH,
)
from digital_scam_shield import scam_detector, preload as preload_scam_model  # noqa: E402

import whisper  # noqa: E402

app = Flask(__name__)
# caller/client (Vite dev, port 5173) and receiver/client (Vite dev, port
# 5174) call this API directly — there is no Node proxy layer in between.
CORS(app, origins=[
    "*",
    re.compile(r"^https?://.*:5173$"),
    re.compile(r"^https?://.*:5174$"),
    re.compile(r"^https?://.*:5175$"),
    re.compile(r"^https?://.*:5176$"),
])
sock = Sock(app)

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
signal_lock = threading.Lock()

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

# WebRTC signaling mailboxes for the *current* session_id only — each side
# posts its own SDP/ICE messages and polls the other side's list with a
# "since" cursor, mirroring the transcript polling pattern above. Cleared
# whenever a new call starts (dial) or the session resets, so stale
# candidates/SDPs from a finished call can never leak into the next one.
signal_state = {
    "session_id": None,
    "caller": [],    # [{index, type: "offer"|"ice", data}]
    "receiver": [],  # [{index, type: "answer"|"ice", data}]
}


def _reset_signal_state_locked(session_id):
    signal_state.update({"session_id": session_id, "caller": [], "receiver": []})


def _on_chunk(timestamp, text):
    """Callback invoked by transcribe_audio() for every finished chunk.

    Returns (score, top_label, risk_status) so transcribe_audio() can write
    the same risk assessment shown on the receiver screen into
    transcription.docx, instead of the docx only ever holding raw text.
    """
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
    return score, top_label, risk_status


def _start_recording():
    """Arms the transcriber for a new call. Audio itself no longer comes
    from a local recorder thread — it's pushed onto audio_queue by
    ws_audio() as the receiver's browser streams PCM frames over
    /ws/audio, so there is nothing to start on that side beyond the
    transcriber thread that drains the queue."""
    global transcriber_thread, is_recording
    with state_lock:
        if is_recording:
            return
        stop_event.clear()
        while not audio_queue.empty():
            audio_queue.get_nowait()

        transcriber_thread = threading.Thread(
            target=transcribe_audio,
            args=(whisper_model,),
            kwargs={"on_chunk": _on_chunk},
            daemon=True,
        )
        transcriber_thread.start()
        is_recording = True

    mark_call_event("Recording started")


def _stop_recording():
    global is_recording
    with state_lock:
        if not is_recording:
            return
        stop_event.set()
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
            "POST /api/call/signal": "post a WebRTC offer/answer/ice message",
            "GET /api/call/signal?session_id=&from=&since=<n>": "poll the other side's WebRTC messages",
            "WS /ws/audio?session_id=": "receiver_ui streams raw PCM16 call audio for transcription",
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

        new_session_id = str(uuid.uuid4())
        session.update({
            "session_id": new_session_id,
            "from_number": from_number,
            "to_number": to_number,
            "status": "ringing",
            "started_at": datetime.now().isoformat(),
            "accepted_at": None,
            "ended_at": None,
        })
        current = dict(session)

    with signal_lock:
        _reset_signal_state_locked(new_session_id)

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
    with signal_lock:
        _reset_signal_state_locked(None)
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


@app.post("/api/call/signal")
def post_signal():
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id")
    role = data.get("role")
    msg_type = data.get("type")
    payload = data.get("data")

    if role not in ("caller", "receiver"):
        return jsonify({"error": "role must be 'caller' or 'receiver'"}), 400
    if msg_type not in ("offer", "answer", "ice"):
        return jsonify({"error": "type must be 'offer', 'answer' or 'ice'"}), 400

    with signal_lock:
        if signal_state["session_id"] != session_id:
            return jsonify({"error": "no matching call for this session_id"}), 409
        mailbox = signal_state[role]
        mailbox.append({"index": len(mailbox), "type": msg_type, "data": payload})

    return jsonify({"ok": True})


@app.get("/api/call/signal")
def get_signal():
    session_id = request.args.get("session_id")
    from_role = request.args.get("from")
    since = request.args.get("since", default=0, type=int)

    if from_role not in ("caller", "receiver"):
        return jsonify({"error": "from must be 'caller' or 'receiver'"}), 400

    with signal_lock:
        if signal_state["session_id"] != session_id:
            return jsonify({"messages": [], "total": 0})
        mailbox = signal_state[from_role]
        messages = mailbox[since:]
        total = len(mailbox)

    return jsonify({"messages": messages, "total": total})


@sock.route("/ws/audio")
def ws_audio(ws):
    """Receives raw 16-bit mono PCM @ RATE Hz streamed from the receiver's
    browser (its own mic mixed with the caller's remote WebRTC track) and
    feeds it into the same audio_queue the old microphone-based
    record_audio() used to fill directly, in ~CHUNK_DURATION-second pieces.

    Chunking (not just relaying raw frames 1:1) happens here rather than in
    the browser because the browser sends small, irregularly-sized frames as
    they're captured; transcribe_audio() expects roughly CHUNK_DURATION of
    audio per item so Whisper has enough context per call to transcribe().
    """
    session_id = request.args.get("session_id")
    with session_lock:
        valid = session["session_id"] == session_id and session["status"] == "active"
    if not valid:
        ws.close()
        return

    assembler = ChunkAssembler()
    try:
        while True:
            data = ws.receive()
            if data is None or not isinstance(data, (bytes, bytearray)):
                break
            for chunk in assembler.add(data):
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                audio_queue.put((timestamp, chunk, False))
    except ConnectionClosed:
        pass
    finally:
        leftover = assembler.flush()
        if leftover:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            audio_queue.put((timestamp, leftover, True))


if __name__ == "__main__":
    # A persisted, shared self-signed cert (see scripts/generate-cert.*) —
    # NOT ssl_context="adhoc". Adhoc mints a brand-new ephemeral cert every
    # process start, which silently invalidates any "proceed anyway" a
    # phone browser had already clicked through the moment the backend
    # restarts, and (like the frontend's old basicSsl plugin) never carried
    # a Subject Alternative Name for the actual IP the phone connects to —
    # which browsers reject outright as a hostname mismatch, no warning to
    # click through at all. That combination is what made the caller UI
    # show "Backend unreachable" even with the process genuinely running.
    cert_path = os.path.join(os.path.dirname(__file__), "..", "certs", "cert.pem")
    key_path = os.path.join(os.path.dirname(__file__), "..", "certs", "key.pem")
    if not (os.path.exists(cert_path) and os.path.exists(key_path)):
        raise SystemExit(
            "TLS certificate not found. Run scripts/generate-cert.sh "
            "(or scripts/generate-cert.ps1 on Windows) first, or `bash setup.sh` / `.\\setup.ps1`."
        )
    app.run(host="0.0.0.0", port=5005, threaded=True, ssl_context=(cert_path, key_path))
