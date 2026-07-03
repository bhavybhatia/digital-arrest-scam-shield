import pyaudio
import socket

HOST = "0.0.0.0"   # listen on all interfaces
PORT = 5001         # must match caller1.py PORT

CHUNK    = 1024
FORMAT   = pyaudio.paInt16
CHANNELS = 1
RATE     = 16000

p = pyaudio.PyAudio()
stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                output=True, frames_per_buffer=CHUNK)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((HOST, PORT))

print(f"[listener1] Listening for audio on port {PORT} ...")
print("[listener1] Press Ctrl+C to stop.\n")

try:
    while True:
        data, addr = sock.recvfrom(CHUNK * 2)   # 2 bytes per sample (paInt16)
        stream.write(data)
except KeyboardInterrupt:
    pass
finally:
    stream.stop_stream()
    stream.close()
    p.terminate()
    sock.close()
    print("\n[listener1] Stopped.")
