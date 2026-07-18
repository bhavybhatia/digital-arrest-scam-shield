import os
import sys
import queue
import threading
import numpy as np
import pyaudio
import whisper
from docx import Document
from datetime import datetime

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK_DURATION = 10   # seconds per chunk
OUTPUT_PATH = "transcription.docx"

audio_queue = queue.Queue()
stop_event = threading.Event()
doc_lock = threading.Lock()


def init_doc():
    if os.path.exists(OUTPUT_PATH):
        print(f"Existing file found: {OUTPUT_PATH} — transcripts will be appended.")
    else:
        doc = Document()
        doc.add_heading("Live Call Transcription Log", level=1)
        doc.save(OUTPUT_PATH)
        print(f"Created new file: {OUTPUT_PATH}")


def _load_or_create_doc():
    try:
        return Document(OUTPUT_PATH)
    except Exception:
        # transcription.docx missing or corrupted (e.g. an earlier crash
        # truncated it mid-write) - recreate it rather than permanently
        # breaking every future append.
        doc = Document()
        doc.add_heading("Live Call Transcription Log", level=1)
        return doc


def append_to_doc(timestamp, text, note=None):
    with doc_lock:
        doc = _load_or_create_doc()
        heading = f"{timestamp}  ({note})" if note else timestamp
        doc.add_paragraph(heading, style="Intense Quote")
        doc.add_paragraph(text)
        doc.save(OUTPUT_PATH)


def mark_call_event(label):
    """Write a call start/end marker into the docx so the fixed ~10s
    transcript chunks are grouped per call instead of reading as one
    continuous, inconsistently-spaced log with unexplained gaps."""
    with doc_lock:
        doc = _load_or_create_doc()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        doc.add_heading(f"— {label} — {timestamp} —", level=2)
        doc.save(OUTPUT_PATH)


def record_audio():
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                    input=True, frames_per_buffer=CHUNK)
    frames_per_chunk = int(RATE / CHUNK * CHUNK_DURATION)

    while not stop_event.is_set():
        frames = []
        for _ in range(frames_per_chunk):
            if stop_event.is_set():
                break
            frames.append(stream.read(CHUNK, exception_on_overflow=False))
        if frames:
            is_partial = len(frames) < frames_per_chunk
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            audio_queue.put((timestamp, b''.join(frames), is_partial))

    stream.stop_stream()
    stream.close()
    p.terminate()


def transcribe_audio(model, on_chunk=None):
    while not stop_event.is_set() or not audio_queue.empty():
        try:
            timestamp, raw, is_partial = audio_queue.get(timeout=1)
        except queue.Empty:
            continue

        try:
            audio_np = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            rms = np.sqrt(np.mean(audio_np ** 2))
            actual_duration = len(audio_np) / RATE
            note = (
                f"{actual_duration:.1f}s partial chunk — call ended mid-recording"
                if is_partial else None
            )

            if rms < 0.001:
                print(f"[{timestamp}] Chunk skipped (silence).")
                continue

            audio_np = audio_np / (np.max(np.abs(audio_np)) + 1e-9) * 0.9
            result = model.transcribe(audio_np, language="en", fp16=False)
            text = result["text"].strip()

            if text:
                print(f"[{timestamp}] >> {text}")
                sys.stdout.flush()
                append_to_doc(timestamp, text, note=note)
                print(f"[{timestamp}] Appended to {OUTPUT_PATH}")
                if on_chunk:
                    on_chunk(timestamp, text)
            else:
                print(f"[{timestamp}] No speech detected in chunk.")
        except Exception as exc:
            # A single bad chunk (transcription error, scoring error, a
            # print() encoding issue, ...) must not kill this thread - that
            # would silently stop all further transcription for the rest of
            # the call with no visible error to the user.
            print(f"[{timestamp}] Chunk processing failed: {exc}")


if __name__ == "__main__":
    # Step 1: Check / create docx
    init_doc()

    # Load model
    print("\nLoading Whisper model (tiny)...")
    model = whisper.load_model("tiny")

    print("\nLive transcription started. Speak freely. Press Ctrl+C to stop.\n")

    recorder = threading.Thread(target=record_audio, daemon=True)
    transcriber = threading.Thread(target=transcribe_audio, args=(model,), daemon=True)

    recorder.start()
    transcriber.start()

    try:
        while recorder.is_alive():
            recorder.join(timeout=0.5)
    except KeyboardInterrupt:
        print("\nStopping... finishing pending transcriptions.")
        stop_event.set()

    recorder.join()
    transcriber.join()
    print(f"\nDone. All transcripts saved to {OUTPUT_PATH}")
