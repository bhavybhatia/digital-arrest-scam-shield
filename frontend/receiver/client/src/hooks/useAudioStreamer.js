import { useEffect, useRef } from "react";

const WS_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ||
  `${window.location.protocol}//${window.location.hostname}:5005`
).replace(/^http/, "ws");

const TARGET_SAMPLE_RATE = 16000;

/**
 * Captures the receiver's own mic plus the caller's incoming WebRTC audio
 * track, mixes them into one mono 16kHz PCM16 stream, and pushes it to the
 * backend over /ws/audio so realtime_transcribe.py can run it through
 * Whisper. This is a separate, backend-only leg — it doesn't touch or
 * replace the browser-to-browser WebRTC call set up by useWebRTCCall.
 */
export function useAudioStreamer({ active, sessionId, remoteStream, deviceId }) {
  const deviceIdRef = useRef(deviceId);
  useEffect(() => {
    deviceIdRef.current = deviceId;
  }, [deviceId]);

  useEffect(() => {
    if (!active || !sessionId || !remoteStream) return undefined;

    let cancelled = false;
    let audioContext = null;
    let micStream = null;
    let processor = null;
    let ws = null;

    async function start() {
      try {
        micStream = await navigator.mediaDevices.getUserMedia({
          audio: deviceIdRef.current ? { deviceId: { exact: deviceIdRef.current } } : true,
        });
        if (cancelled) {
          micStream.getTracks().forEach((t) => t.stop());
          return;
        }

        audioContext = new (window.AudioContext || window.webkitAudioContext)({
          sampleRate: TARGET_SAMPLE_RATE,
        });

        const micSource = audioContext.createMediaStreamSource(micStream);
        const remoteSource = audioContext.createMediaStreamSource(remoteStream);
        const mixer = audioContext.createGain();
        micSource.connect(mixer);
        remoteSource.connect(mixer);

        // ScriptProcessorNode only fires onaudioprocess while connected
        // through to a destination, so it's routed through a muted gain
        // node — the remote track is already audible via the <audio>
        // element WebRTC feeds separately, this tap must stay silent.
        processor = audioContext.createScriptProcessor(4096, 1, 1);
        const silentSink = audioContext.createGain();
        silentSink.gain.value = 0;
        mixer.connect(processor);
        processor.connect(silentSink);
        silentSink.connect(audioContext.destination);

        ws = new WebSocket(
          `${WS_BASE_URL}/ws/audio?session_id=${encodeURIComponent(sessionId)}`
        );
        ws.binaryType = "arraybuffer";

        processor.onaudioprocess = (event) => {
          if (cancelled || !ws || ws.readyState !== WebSocket.OPEN) return;
          const float32 = event.inputBuffer.getChannelData(0);
          const pcm16 = new Int16Array(float32.length);
          for (let i = 0; i < float32.length; i++) {
            const s = Math.max(-1, Math.min(1, float32[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          ws.send(pcm16.buffer);
        };
      } catch (e) {
        // Streaming audio to the backend is best-effort for transcription/
        // risk scoring — a failure here shouldn't interrupt the call itself.
        console.error("useAudioStreamer failed:", e.message);
      }
    }

    start();

    return () => {
      cancelled = true;
      if (processor) processor.onaudioprocess = null;
      if (ws && ws.readyState === WebSocket.OPEN) ws.close();
      if (audioContext) audioContext.close().catch(() => {});
      if (micStream) micStream.getTracks().forEach((t) => t.stop());
    };
  }, [active, sessionId, remoteStream]);
}
