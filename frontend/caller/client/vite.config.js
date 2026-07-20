import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Shared self-signed cert (scripts/generate-cert.sh / .ps1), also used by
// the Flask backend — NOT @vitejs/plugin-basic-ssl, which mints a new
// ephemeral cert every dev-server restart and carries no Subject
// Alternative Name for the LAN/GCP IP a phone actually connects to.
// getUserMedia (mic access) requires a secure context, which plain HTTP
// only gets for free on localhost, not when opened from a phone via LAN IP.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CERT_DIR = path.resolve(__dirname, "../../../certs");
const CERT_PATH = path.join(CERT_DIR, "cert.pem");
const KEY_PATH = path.join(CERT_DIR, "key.pem");

if (!fs.existsSync(CERT_PATH) || !fs.existsSync(KEY_PATH)) {
  throw new Error(
    `TLS certificate not found at ${CERT_DIR}. Run scripts/generate-cert.sh ` +
      `(or scripts/generate-cert.ps1 on Windows) first, or use setup.sh/setup.ps1.`
  );
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,   // bind to 0.0.0.0 so the dev server is reachable from outside the machine
    port: 5173,
    https: {
      cert: fs.readFileSync(CERT_PATH),
      key: fs.readFileSync(KEY_PATH),
    },
  },
});
