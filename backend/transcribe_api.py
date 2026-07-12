import os
import sys
import threading

import whisper
from flask import Flask, jsonify, request

sys.path.insert(0, os.path.dirname(__file__))
from realtime_transcribe import (
    init_doc,
    record_audio,
    transcribe_audio,
    audio_queue,
    stop_event,
    OUTPUT_PATH,
)

app = Flask(__name__)

# Loaded once at startup, before any audio thread starts (loading the model
# concurrently with an active PyAudio stream has been observed to crash).
print("Loading Whisper model (tiny)...")
model = whisper.load_model("tiny")
print("Model loaded.\n")

init_doc()

state_lock = threading.Lock()
log_lock = threading.Lock()

recorder_thread = None
transcriber_thread = None
is_recording = False
transcript_log = []  # list of {"timestamp": str, "text": str}


def _on_chunk(timestamp, text):
    with log_lock:
        transcript_log.append({"timestamp": timestamp, "text": text})


@app.get("/")
def index():
    return jsonify({
        "service": "realtime_transcribe REST API",
        "endpoints": {
            "POST /start": "begin recording + transcribing from the server's microphone",
            "POST /stop": "stop recording and flush pending transcription",
            "GET /transcript?since=<n>": "fetch transcript chunks (all, or only chunks after index n)",
            "GET /status": "current recording state",
        },
    })


@app.post("/start")
def start():
    global recorder_thread, transcriber_thread, is_recording

    with state_lock:
        if is_recording:
            return jsonify({"status": "already_recording"}), 409

        stop_event.clear()
        while not audio_queue.empty():
            audio_queue.get_nowait()

        recorder_thread = threading.Thread(target=record_audio, daemon=True)
        transcriber_thread = threading.Thread(
            target=transcribe_audio, args=(model,), kwargs={"on_chunk": _on_chunk}, daemon=True
        )
        recorder_thread.start()
        transcriber_thread.start()
        is_recording = True

    return jsonify({"status": "recording"})


@app.post("/stop")
def stop():
    global is_recording

    with state_lock:
        if not is_recording:
            return jsonify({"status": "not_recording"}), 409

        stop_event.set()
        recorder_thread.join(timeout=10)
        transcriber_thread.join(timeout=30)
        is_recording = False

    return jsonify({"status": "stopped", "saved_to": OUTPUT_PATH})


@app.get("/transcript")
def transcript():
    since = request.args.get("since", default=0, type=int)
    with log_lock:
        chunks = transcript_log[since:]
        total = len(transcript_log)
    return jsonify({"chunks": chunks, "total": total})


@app.get("/status")
def status():
    with log_lock:
        chunk_count = len(transcript_log)
    return jsonify({
        "recording": is_recording,
        "model_loaded": True,
        "chunks_captured": chunk_count,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, threaded=True)
