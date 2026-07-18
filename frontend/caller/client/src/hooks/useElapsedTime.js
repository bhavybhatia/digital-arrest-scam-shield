import { useEffect, useState } from "react";

/** Presentation-only ticking clock; does not decide when a call starts/ends. */
export function useElapsedTime(startIso) {
  const [elapsed, setElapsed] = useState("00:00");

  useEffect(() => {
    if (!startIso) {
      setElapsed("00:00");
      return undefined;
    }
    const startMs = new Date(startIso).getTime();
    const tick = () => {
      const diff = Math.max(0, Math.floor((Date.now() - startMs) / 1000));
      const mm = String(Math.floor(diff / 60)).padStart(2, "0");
      const ss = String(diff % 60).padStart(2, "0");
      setElapsed(`${mm}:${ss}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startIso]);

  return elapsed;
}
