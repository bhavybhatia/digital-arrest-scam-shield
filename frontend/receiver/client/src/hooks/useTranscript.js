import { useCallback, useEffect, useRef, useState } from "react";
import { callApi } from "../api/client";

/**
 * Polls GET /api/call/transcript?since=n while `active` is true, appending
 * new chunks as they arrive. The scam score / label / risk status on each
 * chunk are computed entirely server-side (scam_analyser.py) — this hook
 * just displays them.
 */
export function useTranscript(active, pollMs = 1500) {
  const [chunks, setChunks] = useState([]);
  const [latest, setLatest] = useState({
    score: 0,
    label: null,
    risk: "\u{1F7E2} LOW RISK",
  });
  const sinceRef = useRef(0);
  const timerRef = useRef(null);

  const poll = useCallback(async () => {
    try {
      const data = await callApi.getTranscript(sinceRef.current);
      if (data.chunks && data.chunks.length) {
        setChunks((prev) => [...prev, ...data.chunks]);
        sinceRef.current = data.total;
      }
      setLatest({
        score: data.latest_score,
        label: data.latest_label,
        risk: data.latest_risk,
      });
    } catch (e) {
      // Transient network hiccups shouldn't crash the call screen.
    }
  }, []);

  useEffect(() => {
    if (!active) return undefined;
    poll();
    timerRef.current = setInterval(poll, pollMs);
    return () => clearInterval(timerRef.current);
  }, [active, poll, pollMs]);

  const reset = useCallback(() => {
    setChunks([]);
    sinceRef.current = 0;
    setLatest({ score: 0, label: null, risk: "\u{1F7E2} LOW RISK" });
  }, []);

  return { chunks, latest, reset };
}
