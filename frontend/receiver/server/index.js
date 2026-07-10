import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import express from "express";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const clientRoot = path.resolve(__dirname, "../client");
const isProduction = process.argv.includes("--prod") || process.env.NODE_ENV === "production";
const PORT = process.env.PORT || 4002;

const app = express();
app.use(express.json());

// In-memory, single-call state — a skeleton standing in for the real
// receiver-side session store until the backend integration pass wires this
// up to the shared call state (see caller/server for its own copy).
let session = {
  session_id: null,
  from_number: null,
  to_number: null,
  status: "idle", // idle | ringing | active | ended | rejected
  started_at: null,
  accepted_at: null,
  ended_at: null,
};

app.get("/api", (req, res) => {
  res.json({
    service: "receiver-server (skeleton)",
    endpoints: {
      "POST /api/call/accept": "accept the ringing call",
      "POST /api/call/decline": "decline the ringing call",
      "POST /api/call/hangup": "end an active call",
      "GET /api/call/session": "poll current call session state",
      "GET /api/call/transcript?since=<n>": "poll transcript + scam risk (mocked)",
    },
  });
});

app.post("/api/call/accept", (req, res) => {
  const { session_id } = req.body || {};

  if (session.session_id !== session_id || session.status !== "ringing") {
    return res.status(409).json({ error: "no matching ringing call" });
  }

  session.status = "active";
  session.accepted_at = new Date().toISOString();
  res.json(session);
});

app.post("/api/call/decline", (req, res) => {
  const { session_id } = req.body || {};

  if (session.session_id !== session_id) {
    return res.status(409).json({ error: "no matching call" });
  }

  session.status = "rejected";
  session.ended_at = new Date().toISOString();
  res.json(session);
});

app.post("/api/call/hangup", (req, res) => {
  const { session_id } = req.body || {};

  if (session.session_id !== session_id) {
    return res.status(409).json({ error: "no matching call" });
  }

  session.status = "ended";
  session.ended_at = new Date().toISOString();
  res.json(session);
});

app.get("/api/call/session", (req, res) => {
  res.json(session);
});

app.get("/api/call/transcript", (req, res) => {
  // No transcription/scam-analyser wiring yet — this is a placeholder shape
  // matching the real backend's response until that integration lands.
  res.json({
    chunks: [],
    total: 0,
    latest_score: 0,
    latest_label: null,
    latest_risk: "\u{1F7E2} LOW RISK",
    saved_to: null,
  });
});

async function start() {
  if (isProduction) {
    app.use(express.static(path.join(clientRoot, "dist")));
    app.get(/^(?!\/api).*/, (req, res) => {
      res.sendFile(path.join(clientRoot, "dist", "index.html"));
    });
    app.listen(PORT, () => {
      console.log(`receiver app (production) listening on http://localhost:${PORT}`);
    });
    return;
  }

  // Dev mode: bind Vite's HMR websocket to our own HTTP server instead of
  // letting it fall back to its own default port (24678) — that fallback
  // port is shared process-wide, so the caller app's dev server would
  // collide with it and its HMR client would flap against the wrong app.
  // `hmr.port` must also be set explicitly: without it, the browser-side
  // client falls back to vite.config.js's `server.port` (5174) to build its
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
    console.log(`receiver app (dev) listening on http://localhost:${PORT}`);
  });
}

start();
