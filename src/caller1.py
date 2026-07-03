import os
import sys
import pyaudio
import socket
import queue
import threading
import numpy as np
import whisper
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from realtime_transcribe import init_doc, append_to_doc

LISTENER_HOST  = "127.0.0.1"
LISTENER_PORT  = 5001

CHUNK          = 1024
FORMAT         = pyaudio.paInt16
CHANNELS       = 1
RATE           = 16000
CHUNK_DURATION = 10   # seconds of audio per transcription batch

audio_queue = queue.Queue()
stop_event  = threading.Event()


def stream_and_capture():
    p = pyaudio.PyAudio()
    mic = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                 input=True, frames_per_buffer=CHUNK)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    frames_per_batch = int(RATE / CHUNK * CHUNK_DURATION)

    print(f"[caller1] Streaming to {LISTENER_HOST}:{LISTENER_PORT}")
    print("[caller1] Transcription active. Speak freely. Press Ctrl+C to stop.\n")

    while not stop_event.is_set():
        frames = []
        for _ in range(frames_per_batch):
            if stop_event.is_set():
                break
            data = mic.read(CHUNK, exception_on_overflow=False)
            sock.sendto(data, (LISTENER_HOST, LISTENER_PORT))  # relay immediately
            frames.append(data)
        if frames:
            audio_queue.put(b"".join(frames))  # queue for transcription

    mic.stop_stream()
    mic.close()
    p.terminate()
    sock.close()


def transcribe(model):
    while not stop_event.is_set() or not audio_queue.empty():
        try:
            raw = audio_queue.get(timeout=1)
        except queue.Empty:
            continue

        audio_np = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        rms = np.sqrt(np.mean(audio_np ** 2))

        if rms < 0.001:
            print("[caller1] (silence — skipped)")
            continue

        audio_np = audio_np / (np.max(np.abs(audio_np)) + 1e-9) * 0.9
        result = model.transcribe(audio_np, language="en", fp16=False)
        text = result["text"].strip()

        if text:
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] >> {text}")
            append_to_doc(ts, text)


# Init docx (creates transcription.docx if it doesn't exist, appends if it does)
init_doc()

# Load Whisper model once before starting threads
print("[caller1] Loading Whisper model (tiny)...")
model = whisper.load_model("tiny")
print("[caller1] Model loaded.\n")

capture_thread    = threading.Thread(target=stream_and_capture, daemon=True)
transcribe_thread = threading.Thread(target=transcribe, args=(model,), daemon=True)

capture_thread.start()
transcribe_thread.start()

try:
    while capture_thread.is_alive():
        capture_thread.join(timeout=0.5)
except KeyboardInterrupt:
    print("\n[caller1] Stopping...")
    stop_event.set()

capture_thread.join()
transcribe_thread.join()
print("[caller1] Done.")
