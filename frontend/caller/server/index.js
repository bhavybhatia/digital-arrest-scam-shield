import { randomUUID } from "node:crypto";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import express from "express";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const clientRoot = path.resolve(__dirname, "../client");
const isProduction = process.argv.includes("--prod") || process.env.NODE_ENV === "production";
const PORT = process.env.PORT || 4001;

// transcribe_api.py (backend/transcribe_api.py) — standalone Flask API that
// captures audio from the backend machine's microphone, transcribes it with
// Whisper, and appends each chunk to backend/transcription.docx. It knows
// nothing about call sessions; this server is the one deciding *when* to
// tell it to start/stop.
const TRANSCRIBE_API_URL = process.env.TRANSCRIBE_API_URL || "http://localhost:5005";

const app = express();
app.use(express.json());

async function callTranscribeApi(apiPath, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(`${TRANSCRIBE_API_URL}${apiPath}`, { ...options, signal: controller.signal });
    const data = await res.json().catch(() => ({}));
    if (!res.ok && res.status !== 409) {
      console.error(`transcribe_api ${apiPath} failed (${res.status}):`, data);
    }
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    console.error(`transcribe_api ${apiPath} unreachable:`, err.message);
    return { ok: false, status: 0, data: null };
  } finally {
    clearTimeout(timeout);
  }
}

function startTranscription() {
  // Fire-and-forget: the dial response shouldn't block on the Python
  // backend spinning up its recorder/transcriber threads, and a
  // stopped/unreachable transcribe_api.py must never break the call flow.
  callTranscribeApi("/start", { method: "POST" });
}

function stopTranscription() {
  // Fire-and-forget: transcribe_api.py's /stop joins the transcriber thread
  // (up to ~30s if a Whisper chunk is mid-flight) before responding —
  // awaiting that here would make hangup/decline appear to hang in the UI.
  // Safe to call defensively on every terminal path (matches app.py's own
  // "stop it if it somehow is recording" pattern); a 409 when nothing is
  // recording is expected and harmless.
  callTranscribeApi("/stop", { method: "POST" });
}

// In-memory, single-call state — a skeleton standing in for the real
// caller-side session store until the backend integration pass wires this
// up to the shared call state (see receiver/server for its own copy).
let session = {
  session_id: null,
  from_number: null,
  to_number: null,
  status: "idle", // idle | ringing | active | ended | rejected
  started_at: null,
  accepted_at: null,
  ended_at: null,
};

function resetSession() {
  session = {
    session_id: null,
    from_number: null,
    to_number: null,
    status: "idle",
    started_at: null,
    accepted_at: null,
    ended_at: null,
  };
}

app.get("/api", (req, res) => {
  res.json({
    service: "caller-server (skeleton)",
    endpoints: {
      "POST /api/call/dial": "place a call to a number (starts transcription)",
      "POST /api/call/decline": "cancel a ringing outgoing call (stops transcription)",
      "POST /api/call/hangup": "end an active call (stops transcription)",
      "POST /api/call/reset": "clear a finished call back to idle (stops transcription)",
      "GET /api/call/session": "poll current call session state",
      "GET /api/call/transcript": "proxy of transcribe_api.py's /transcript",
      "GET /api/call/transcription-status": "proxy of transcribe_api.py's /status",
    },
  });
});

app.post("/api/call/dial", (req, res) => {
  const toNumber = (req.body?.to_number || "").trim();
  const fromNumber = (req.body?.from_number || "Unknown").trim();

  if (!toNumber) {
    return res.status(400).json({ error: "to_number is required" });
  }

  if (session.status === "ringing" || session.status === "active") {
    return res.status(409).json({ error: "a call is already in progress" });
  }

  session = {
    session_id: randomUUID(),
    from_number: fromNumber,
    to_number: toNumber,
    status: "ringing",
    started_at: new Date().toISOString(),
    accepted_at: null,
    ended_at: null,
  };

  startTranscription();
  res.json(session);
});

app.post("/api/call/decline", (req, res) => {
  const { session_id } = req.body || {};

  if (session.session_id !== session_id) {
    return res.status(409).json({ error: "no matching call" });
  }

  session.status = "rejected";
  session.ended_at = new Date().toISOString();
  stopTranscription();
  res.json(session);
});

app.post("/api/call/hangup", (req, res) => {
  const { session_id } = req.body || {};

  if (session.session_id !== session_id) {
    return res.status(409).json({ error: "no matching call" });
  }

  session.status = "ended";
  session.ended_at = new Date().toISOString();
  stopTranscription();
  res.json(session);
});

app.post("/api/call/reset", (req, res) => {
  resetSession();
  stopTranscription();
  res.json(session);
});

app.get("/api/call/session", (req, res) => {
  res.json(session);
});

app.get("/api/call/transcript", async (req, res) => {
  const since = req.query.since ?? 0;
  const { ok, status, data } = await callTranscribeApi(`/transcript?since=${encodeURIComponent(since)}`);
  if (!ok) {
    return res.status(502).json({ error: "transcribe_api unreachable", chunks: [], total: 0 });
  }
  res.status(status).json(data);
});

app.get("/api/call/transcription-status", async (req, res) => {
  const { ok, status, data } = await callTranscribeApi("/status");
  if (!ok) {
    return res.status(502).json({ error: "transcribe_api unreachable", recording: false });
  }
  res.status(status).json(data);
});

async function start() {
  if (isProduction) {
    app.use(express.static(path.join(clientRoot, "dist")));
    app.get(/^(?!\/api).*/, (req, res) => {
      res.sendFile(path.join(clientRoot, "dist", "index.html"));
    });
    app.listen(PORT, () => {
      console.log(`caller app (production) listening on http://localhost:${PORT}`);
    });
    return;
  }

  // Dev mode: bind Vite's HMR websocket to our own HTTP server instead of
  // letting it fall back to its own default port (24678) — that fallback
  // port is shared process-wide, so the receiver app's dev server would
  // collide with it and its HMR client would flap against the wrong app.
  // `hmr.port` must also be set explicitly: without it, the browser-side
  // client falls back to vite.config.js's `server.port` (5173) to build its
  // websocket URL, which is never actually listening since we bypass vite's
  // own listen() in favor of this http.Server on PORT.
  const httpServer = http.createServer(app);
  const { createServer: createViteServer } = await import("vite");
  const vite = await createViteServer({
    root: clientRoot,
    server: { middlewareMode: true, hmr: { server: httpServer, port: PORT } },
    appType: "spa",
  });
  app.use(vite.middlewares);

  httpServer.listen(PORT, () => {
    console.log(`caller app (dev) listening on http://localhost:${PORT}`);
  });
}

start();
