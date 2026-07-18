const BASE_URL = import.meta.env.VITE_API_BASE_URL ||
  `${window.location.protocol}//${window.location.hostname}:5005`;

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed with status ${res.status}`);
  }
  return data;
}

// Every one of these is a dumb pass-through to the backend. The React
// components never decide *what* a call status means or *how* risk is
// scored — they only render whatever the backend tells them.
export const callApi = {
  dial: (toNumber, fromNumber) =>
    request("/api/call/dial", {
      method: "POST",
      body: JSON.stringify({ to_number: toNumber, from_number: fromNumber }),
    }),

  accept: (sessionId) =>
    request("/api/call/accept", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),

  decline: (sessionId) =>
    request("/api/call/decline", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),

  hangup: (sessionId) =>
    request("/api/call/hangup", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),

  reset: () => request("/api/call/reset", { method: "POST" }),

  getSession: () => request("/api/call/session"),

  getTranscript: (since = 0) => request(`/api/call/transcript?since=${since}`),
};
