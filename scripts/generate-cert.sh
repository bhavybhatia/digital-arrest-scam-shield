#!/bin/bash
# Generates ONE self-signed cert (certs/cert.pem + certs/key.pem) shared by
# the Flask backend and both Vite dev servers.
#
# Why a shared, persisted cert instead of what was there before:
#   - Flask's ssl_context="adhoc" and Vite's @vitejs/plugin-basic-ssl each
#     mint a brand-new ephemeral self-signed cert every process start. Any
#     phone that had previously clicked through the "not secure" warning
#     loses that trust the instant the backend/dev server restarts, which
#     silently breaks fetch()/WebSocket calls again (no interactive prompt
#     for those — they just fail, showing up as "Backend unreachable" even
#     though the process is genuinely running).
#   - Neither of those ephemeral certs carries a Subject Alternative Name
#     for the actual host the phone connects to (a GCP VM's external IP, or
#     a LAN IP), which modern browsers reject outright as a hostname
#     mismatch — not even a click-through warning, a hard failure.
#
# This script generates one cert with proper SAN entries (localhost, LAN
# IP(s), and — when run on a GCP VM — the instance's external IP via the
# metadata server) and writes it once; re-runs are a no-op unless
# FORCE_REGEN=1 is set.
set -e

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/certs"
mkdir -p "$CERT_DIR"
CERT="$CERT_DIR/cert.pem"
KEY="$CERT_DIR/key.pem"

if [ -f "$CERT" ] && [ -f "$KEY" ] && [ "$FORCE_REGEN" != "1" ]; then
  echo "TLS certificate already exists at $CERT_DIR (set FORCE_REGEN=1 to regenerate)."
  exit 0
fi

SAN="DNS:localhost,IP:127.0.0.1"

for ip in $(hostname -I 2>/dev/null || true); do
  SAN="$SAN,IP:$ip"
done

# GCP metadata server — only reachable from inside a GCP VM, so this is a
# harmless quick no-op everywhere else.
GCP_IP=$(curl -s --max-time 1 -H "Metadata-Flavor: Google" \
  "http://169.254.169.254/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip" 2>/dev/null || true)
if [ -n "$GCP_IP" ]; then
  SAN="$SAN,IP:$GCP_IP"
  echo "Detected GCP external IP: $GCP_IP"
fi

# Comma-separated extra IPs/hostnames the caller wants trusted, e.g.
#   EXTRA_SAN=203.0.113.10 bash scripts/generate-cert.sh
if [ -n "$EXTRA_SAN" ]; then
  IFS=',' read -ra EXTRA <<< "$EXTRA_SAN"
  for entry in "${EXTRA[@]}"; do
    SAN="$SAN,IP:$entry"
  done
fi

echo "Generating self-signed cert with SAN: $SAN"
# The doubled leading slash on -subj is a Git-Bash-on-Windows workaround:
# MSYS mangles a single leading "/" into a Windows path (breaking openssl's
# "/CN=..." syntax); "//CN=..." survives that conversion intact. It's a
# no-op on real Linux/macOS bash (the GCP Debian target), where paths are
# never rewritten.
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$KEY" -out "$CERT" \
  -days 825 \
  -subj "//CN=digital-arrest-scam-shield" \
  -addext "subjectAltName=$SAN"

echo "Certificate written to $CERT_DIR"
