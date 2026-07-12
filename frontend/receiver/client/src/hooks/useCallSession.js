import { useCallback, useEffect, useRef, useState } from "react";
import { callApi } from "../api/client";

/**
 * Polls GET /api/call/session so both phone screens stay in sync with the
 * single source of truth (the Flask backend). No call-state decisions are
 * made here — this hook only fetches and exposes whatever the backend says.
 */
export function useCallSession(pollMs = 1000) {
  const [session, setSession] = useState(null);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const data = await callApi.getSession();
      setSession(data);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    refresh();
    timerRef.current = setInterval(refresh, pollMs);
    return () => clearInterval(timerRef.current);
  }, [refresh, pollMs]);

  return { session, error, refresh };
}
