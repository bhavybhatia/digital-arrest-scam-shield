import { useEffect, useRef, useState } from "react";
import { signalApi } from "../api/client";

// STUN alone can't traverse symmetric/carrier-grade NAT, which is common
// when caller and receiver are on separate public networks (e.g. two
// phones on mobile data hitting a GCP-hosted deployment) rather than the
// same LAN. A TURN relay is required for that case. VITE_TURN_DOMAIN +
// VITE_TURN_API_KEY (from .env.local, see .env.local.example) are Metered's
// account credentials for *minting* short-lived TURN username/password
// pairs via their REST API - they are not a TURN username/credential
// themselves, so servers must be fetched fresh per call rather than
// hardcoded. Falls back to STUN-only if unset or the fetch fails.
async function fetchIceServers() {
  const fallback = [{ urls: "stun:stun.l.google.com:19302" }];
  const domain = import.meta.env.VITE_TURN_DOMAIN;
  const apiKey = import.meta.env.VITE_TURN_API_KEY;
  if (!domain || !apiKey) return fallback;

  try {
    const res = await fetch(
      `https://${domain}/api/v1/turn/credentials?apiKey=${apiKey}`
    );
    if (!res.ok) return fallback;
    const servers = await res.json();
    return Array.isArray(servers) && servers.length ? servers : fallback;
  } catch (e) {
    return fallback;
  }
}
const POLL_MS = 700;

/**
 * Sets up a real WebRTC audio call once `active` is true, using the shared
 * signaling mailboxes in the backend (api/client.js `signalApi`) to exchange
 * the SDP offer/answer and trickle ICE candidates. `role` is fixed per app
 * (this app is always "caller" or always "receiver") — the caller creates
 * the offer, the receiver answers it, and each side polls the *other*
 * role's mailbox for new messages.
 *
 * The selected mic device is locked in at call start (read once from a ref)
 * so changing the dropdown mid-call doesn't tear down an active connection.
 */
export function useWebRTCCall({ active, role, sessionId, deviceId }) {
  const [remoteStream, setRemoteStream] = useState(null);
  const [connectionState, setConnectionState] = useState("idle");
  const [error, setError] = useState(null);

  const deviceIdRef = useRef(deviceId);
  useEffect(() => {
    deviceIdRef.current = deviceId;
  }, [deviceId]);

  useEffect(() => {
    if (!active || !sessionId || !role) return undefined;

    let cancelled = false;
    let pc = null;
    let localStream = null;
    let pollTimer = null;
    let remoteDescSet = false;
    let pendingIce = [];
    let since = 0;
    const otherRole = role === "caller" ? "receiver" : "caller";

    async function flushPendingIce() {
      const queued = pendingIce;
      pendingIce = [];
      for (const candidate of queued) {
        await pc.addIceCandidate(candidate).catch(() => {});
      }
    }

    async function poll() {
      try {
        const { messages, total } = await signalApi.poll(sessionId, otherRole, since);
        since = total;
        for (const msg of messages) {
          if (msg.type === "offer" && role === "receiver") {
            await pc.setRemoteDescription(new RTCSessionDescription(msg.data));
            remoteDescSet = true;
            await flushPendingIce();
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            await signalApi.send(sessionId, role, "answer", answer);
          } else if (msg.type === "answer" && role === "caller") {
            await pc.setRemoteDescription(new RTCSessionDescription(msg.data));
            remoteDescSet = true;
            await flushPendingIce();
          } else if (msg.type === "ice") {
            const candidate = new RTCIceCandidate(msg.data);
            if (remoteDescSet) {
              await pc.addIceCandidate(candidate).catch(() => {});
            } else {
              pendingIce.push(candidate);
            }
          }
        }
      } catch (e) {
        // Transient network hiccups shouldn't tear down the call.
      }
    }

    async function start() {
      try {
        setConnectionState("connecting");
        setError(null);

        const deviceId_ = deviceIdRef.current;
        localStream = await navigator.mediaDevices.getUserMedia({
          audio: deviceId_ ? { deviceId: { exact: deviceId_ } } : true,
        });
        if (cancelled) {
          localStream.getTracks().forEach((t) => t.stop());
          return;
        }

        const iceServers = await fetchIceServers();
        if (cancelled) {
          localStream.getTracks().forEach((t) => t.stop());
          return;
        }
        pc = new RTCPeerConnection({ iceServers });
        localStream.getTracks().forEach((track) => pc.addTrack(track, localStream));

        pc.ontrack = (event) => {
          if (!cancelled) setRemoteStream(event.streams[0]);
        };

        pc.onconnectionstatechange = () => {
          if (!cancelled && pc) setConnectionState(pc.connectionState);
        };

        pc.onicecandidate = (event) => {
          if (event.candidate) {
            signalApi.send(sessionId, role, "ice", event.candidate.toJSON()).catch(() => {});
          }
        };

        if (role === "caller") {
          const offer = await pc.createOffer();
          await pc.setLocalDescription(offer);
          await signalApi.send(sessionId, role, "offer", offer);
        }

        poll();
        pollTimer = setInterval(poll, POLL_MS);
      } catch (e) {
        if (!cancelled) {
          setError(e.message);
          setConnectionState("failed");
        }
      }
    }

    start();

    return () => {
      cancelled = true;
      clearInterval(pollTimer);
      if (pc) pc.close();
      if (localStream) localStream.getTracks().forEach((t) => t.stop());
      setRemoteStream(null);
      setConnectionState("idle");
    };
  }, [active, role, sessionId]);

  return { remoteStream, connectionState, error };
}
