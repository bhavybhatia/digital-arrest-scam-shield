import { useEffect, useRef } from "react";
import PhoneFrame from "../components/PhoneFrame.jsx";
import RiskMeter from "../components/RiskMeter.jsx";
import TranscriptFeed from "../components/TranscriptFeed.jsx";
import { useCallSession } from "../hooks/useCallSession.js";
import { useTranscript } from "../hooks/useTranscript.js";
import { useElapsedTime } from "../hooks/useElapsedTime.js";
import { callApi } from "../api/client.js";
import { isSamePhoneNumber } from "../utils/phoneNumber.js";

const OWN_NUMBER = import.meta.env.VITE_RECEIVER_NUMBER || "+91 98765 43210";

export default function ReceiverPhone() {
  const { session } = useCallSession(1000);

  const isForMe = session && isSamePhoneNumber(session.to_number, OWN_NUMBER);
  const status = isForMe ? session.status : "idle";
  const elapsed = useElapsedTime(isForMe ? session.accepted_at : null);
  const { chunks, latest, reset } = useTranscript(status === "active", 1500);

  // This component never unmounts between calls, so useTranscript's state
  // (chunks, the polling "since" cursor) would otherwise keep carrying over
  // from the previous call. Every dial() gets a fresh session_id, so
  // resetting the moment a new one starts ringing clears the screen exactly
  // once per call, before "In call" ever renders — the just-ended call's
  // "Call ended" summary (shown only while status is rejected/ended) is
  // unaffected since ringing replaces that screen anyway.
  const resetForSessionRef = useRef(null);
  useEffect(() => {
    const sessionId = isForMe ? session?.session_id : null;
    if (status === "ringing" && sessionId && resetForSessionRef.current !== sessionId) {
      reset();
      resetForSessionRef.current = sessionId;
    }
  }, [isForMe, session?.session_id, status, reset]);

  const accept = () =>
    session &&
    callApi
      .accept(session.session_id)
      .catch((e) => console.error("callApi.accept failed:", e.message));
  const decline = () =>
    session &&
    callApi
      .decline(session.session_id)
      .catch((e) => console.error("callApi.decline failed:", e.message));
  const hangup = () =>
    session &&
    callApi
      .hangup(session.session_id)
      .catch((e) => console.error("callApi.hangup failed:", e.message));

  const content = () => {
    if (!session) return <div className="phone-loading">Connecting to backend…</div>;

    if (status === "ringing") {
      return (
        <div className="call-status-screen">
          <div className="call-avatar call-avatar-ringing">📞</div>
          <div className="call-title">Incoming call</div>
          <div className="call-subtitle">{session.from_number}</div>
          <div className="incoming-actions">
            <button className="btn btn-danger btn-round" onClick={decline}>
              ✕
            </button>
            <button className="btn btn-call btn-round" onClick={accept}>
              📞
            </button>
          </div>
        </div>
      );
    }

    if (status === "active") {
      return (
        <div className="in-call-screen">
          <div className="call-title">In call</div>
          <div className="call-subtitle">{session.from_number}</div>
          <div className="call-timer">{elapsed}</div>

          <RiskMeter score={latest.score} label={latest.label} risk={latest.risk} />

          <TranscriptFeed chunks={chunks} />

          <button className="btn btn-danger btn-wide" onClick={hangup}>
            End Call
          </button>
        </div>
      );
    }

    if (status === "rejected" || status === "ended") {
      return (
        <div className="call-status-screen">
          <div className="call-title">Call ended</div>
          {chunks.length > 0 && (
            <div className="call-summary">
              <RiskMeter score={latest.score} label={latest.label} risk={latest.risk} />
              <div className="call-summary-note">
                Final risk assessment for this call. Full transcript saved to
                transcription.docx.
              </div>
            </div>
          )}
        </div>
      );
    }

    return (
      <div className="call-status-screen">
        <div className="call-title">Waiting for calls…</div>
        <div className="call-subtitle">Your number: {OWN_NUMBER}</div>
      </div>
    );
  };

  const body = (
    <div className="phone-app">
      <div className="phone-app-header">Receiver</div>
      {content()}
    </div>
  );

  return <PhoneFrame label="Receiver Phone">{body}</PhoneFrame>;
}
