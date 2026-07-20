import { useEffect, useRef, useState } from "react";
import PhoneFrame from "../components/PhoneFrame.jsx";
import Dialpad from "../components/Dialpad.jsx";
import AudioDeviceSelect from "../components/AudioDeviceSelect.jsx";
import { useCallSession } from "../hooks/useCallSession.js";
import { useElapsedTime } from "../hooks/useElapsedTime.js";
import { useAudioDevices } from "../hooks/useAudioDevices.js";
import { useWebRTCCall } from "../hooks/useWebRTCCall.js";
import { callApi } from "../api/client.js";
import { isSamePhoneNumber } from "../utils/phoneNumber.js";

const OWN_NUMBER = import.meta.env.VITE_CALLER_NUMBER || "+91 90000 00001";
const RECEIVER_HINT = `Try dialing the receiver: ${
  import.meta.env.VITE_RECEIVER_NUMBER || "+91 98765 43210"
}`;

export default function CallerPhone() {
  const { session, error } = useCallSession(1000);
  const resetFiredRef = useRef(false);
  const [dialError, setDialError] = useState(null);

  const isMine =
    session && isSamePhoneNumber(session.from_number, OWN_NUMBER); // only render call state we originated
  const status = isMine ? session.status : "idle";
  const elapsed = useElapsedTime(isMine ? session.accepted_at : null);

  const audioDevices = useAudioDevices();
  const audioRef = useRef(null);
  const { remoteStream, connectionState } = useWebRTCCall({
    active: isMine && status === "active",
    role: "caller",
    sessionId: isMine ? session?.session_id : null,
    deviceId: audioDevices.selectedDeviceId,
  });

  useEffect(() => {
    if (audioRef.current) audioRef.current.srcObject = remoteStream || null;
  }, [remoteStream]);

  // Once a call this phone placed finishes, auto reset the shared session
  // after a short delay so the dialpad reappears for the next demo run.
  useEffect(() => {
    if (isMine && (status === "ended" || status === "rejected") && !resetFiredRef.current) {
      resetFiredRef.current = true;
      const t = setTimeout(() => {
        callApi.reset().catch(() => {});
      }, 2000);
      return () => clearTimeout(t);
    }
    if (status === "idle") {
      resetFiredRef.current = false;
    }
    return undefined;
  }, [isMine, status]);

  useEffect(() => {
    if (status === "ringing") setDialError(null);
  }, [status]);

  const placeCall = async (number) => {
    try {
      setDialError(null);
      await callApi.dial(number, OWN_NUMBER);
    } catch (e) {
      // A call already in progress, etc. — surfaced via banner below.
      console.error("callApi.dial failed:", e.message);
      setDialError(e.message);
    }
  };

  const cancelOrHangup = async () => {
    if (!session) return;
    if (status === "ringing") {
      await callApi.decline(session.session_id).catch(() => {});
    } else if (status === "active") {
      await callApi.hangup(session.session_id).catch(() => {});
    }
  };

  const content = () => {
    if (!session) return <div className="phone-loading">Connecting to backend…</div>;

    if (status === "ringing") {
      return (
        <div className="call-status-screen">
          <div className="call-avatar">📱</div>
          <div className="call-title">Calling…</div>
          <div className="call-subtitle">{session.to_number}</div>
          <button className="btn btn-danger btn-wide" onClick={cancelOrHangup}>
            Cancel
          </button>
        </div>
      );
    }

    if (status === "active") {
      return (
        <div className="call-status-screen">
          <div className="call-avatar call-avatar-active">📱</div>
          <div className="call-title">In call</div>
          <div className="call-subtitle">{session.to_number}</div>
          <div className="call-timer">{elapsed}</div>
          {connectionState !== "connected" && (
            <div className="call-subtitle">Audio: {connectionState}…</div>
          )}
          <button className="btn btn-danger btn-wide" onClick={cancelOrHangup}>
            End Call
          </button>
        </div>
      );
    }

    if (status === "rejected") {
      return (
        <div className="call-status-screen">
          <div className="call-title">Call declined</div>
          <div className="call-subtitle">{session.to_number}</div>
        </div>
      );
    }

    if (status === "ended") {
      return (
        <div className="call-status-screen">
          <div className="call-title">Call ended</div>
          <div className="call-subtitle">{session.to_number}</div>
        </div>
      );
    }

    return (
      <>
        <AudioDeviceSelect
          devices={audioDevices.devices}
          selectedDeviceId={audioDevices.selectedDeviceId}
          onChange={audioDevices.setSelectedDeviceId}
          permission={audioDevices.permission}
          onRequestPermission={audioDevices.requestPermission}
          error={audioDevices.error}
        />
        <Dialpad ownNumber={OWN_NUMBER} hint={RECEIVER_HINT} onCall={placeCall} />
      </>
    );
  };

  const body = (
    <div className="phone-app">
      <div className="phone-app-header">Caller</div>
      {error && <div className="phone-error">Backend unreachable</div>}
      {!error && dialError && <div className="phone-error">{dialError}</div>}
      {content()}
      <audio ref={audioRef} autoPlay />
    </div>
  );

  return <PhoneFrame label="Caller Phone">{body}</PhoneFrame>;
}
