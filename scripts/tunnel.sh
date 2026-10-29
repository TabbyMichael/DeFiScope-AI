#!/usr/bin/env bash
#
# DeFiScope AI - Cloudflare Quick Tunnel helper.
#
# Exposes the locally-running app on a public, shareable https://*.trycloudflare.com
# URL so external users can view it without any port-forwarding, firewall rules or a
# Cloudflare account. Quick tunnels are ephemeral: the URL changes every run and
# stops working the moment you Ctrl+C this script.
#
# Usage:
#   bash scripts/tunnel.sh                 # auto-detect ports, tunnel web (+ api)
#   bash scripts/tunnel.sh --web 3000      # force the web dev port
#   bash scripts/tunnel.sh --no-api        # tunnel only the web app
#   WEB_PORT=4000 API_PORT=3646 bash scripts/tunnel.sh
#
# Ports default to the docker-compose mapping (web :4000, api :3646); if those
# aren't listening it falls back to the local dev ports (web :3000, api :8000).
#
set -euo pipefail

# --- Config -------------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$REPO_ROOT/.cloudflared-bin"
TUNNEL_BIN="${TUNNEL_BIN:-$BIN_DIR/cloudflared}"
LOG_DIR="$(mktemp -d)"
RELEASES="https://github.com/cloudflare/cloudflared/releases/latest/download"

# Defaults (overridable via env or flags below).
WEB_PORT="${WEB_PORT:-}"
API_PORT="${API_PORT:-}"
TUNNEL_API=1

CLEANED=0
cleanup() {
  # Idempotent teardown, run exactly once from the EXIT trap.
  (( CLEANED )) && return
  CLEANED=1
  # Kill any cloudflared children we spawned and drop the temp logs.
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  rm -rf "$LOG_DIR"
}
# Signals just exit; the EXIT trap does the single cleanup pass (no double-fire).
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

log()  { printf '%s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
DeFiScope AI - Cloudflare Quick Tunnel helper.

Publishes the locally-running app on a public https://*.trycloudflare.com URL.
Ephemeral: the URL changes each run and stops when you Ctrl+C.

Usage:
  bash scripts/tunnel.sh                 # auto-detect ports, tunnel web (+ api)
  bash scripts/tunnel.sh --web 3000      # force the web port
  bash scripts/tunnel.sh --api 8000      # force the API port
  bash scripts/tunnel.sh --no-api        # tunnel only the web app
  bash scripts/tunnel.sh --help          # show this help

Env overrides: WEB_PORT, API_PORT, TUNNEL_BIN (path to a cloudflared binary).
USAGE
}

# --- Arg parsing --------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --web)    WEB_PORT="${2:?--web needs a port}"; shift 2 ;;
    --api)    API_PORT="${2:?--api needs a port}"; shift 2 ;;
    --no-api) TUNNEL_API=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1 (see --help)" ;;
  esac
done

# --- Helpers ------------------------------------------------------------------
# Is something already listening on 127.0.0.1:<port>?
port_open() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

# Pick the first candidate port that is actually serving.
detect_port() {
  for cand in "$@"; do
    if port_open "$cand"; then printf '%s' "$cand"; return 0; fi
  done
  return 1
}

install_cloudflared() {
  [[ -x "$TUNNEL_BIN" ]] && return 0
  command -v cloudflared >/dev/null 2>&1 && { TUNNEL_BIN="$(command -v cloudflared)"; return 0; }

  log "cloudflared not found - downloading into $BIN_DIR ..."
  local os arch asset tmp
  os="$(uname -s)"
  arch="$(uname -m)"
  mkdir -p "$BIN_DIR"
  case "$os" in
    Linux)
      case "$arch" in
        x86_64|amd64) asset="cloudflared-linux-amd64" ;;
        aarch64|arm64) asset="cloudflared-linux-arm64" ;;
        *) die "Unsupported Linux arch: $arch" ;;
      esac
      curl -fsSL "$RELEASES/$asset" -o "$BIN_DIR/cloudflared"
      chmod +x "$BIN_DIR/cloudflared"
      ;;
    Darwin)
      case "$arch" in
        x86_64) asset="cloudflared-darwin-amd64.tgz" ;;
        arm64)  asset="cloudflared-darwin-arm64.tgz" ;;
        *) die "Unsupported macOS arch: $arch" ;;
      esac
      tmp="$BIN_DIR/$asset"
      curl -fsSL "$RELEASES/$asset" -o "$tmp"
      tar -xzf "$tmp" -C "$BIN_DIR" cloudflared
      rm -f "$tmp"
      chmod +x "$BIN_DIR/cloudflared"
      ;;
    *) die "Unsupported OS: $os (install cloudflared manually and set TUNNEL_BIN)" ;;
  esac
}

# Launch a quick tunnel for one local port; sets TUNNEL_URL once it reports a
# hostname. Runs in the CURRENT shell (no subshell) so the cloudflared process
# and its PID stay in the parent's job table for `wait`/cleanup to work.
# Args: <name> <port>
start_tunnel() {
  local name="$1" port="$2" url="" waited=0
  local logfile="$LOG_DIR/$name.log"
  TUNNEL_URL=""
  "$TUNNEL_BIN" tunnel \
    --url "http://localhost:$port" \
    --no-autoupdate \
    >"$logfile" 2>&1 &
  local pid=$!
  PIDS+=("$pid")

  # cloudflared prints the assigned hostname within a few seconds.
  while (( waited < 45 )); do
    if ! kill -0 "$pid" 2>/dev/null; then
      warn "$name tunnel process exited early; log tail:"
      tail -n 20 "$logfile" >&2 || true
      return 1
    fi
    url="$(grep -Eo 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$logfile" | head -n1 || true)"
    if [[ -n "$url" ]]; then TUNNEL_URL="$url"; return 0; fi
    sleep 1; waited=$((waited + 1))
  done
  warn "$name tunnel did not report a URL within 45s; log tail:"
  tail -n 20 "$logfile" >&2 || true
  return 1
}

# --- Main ---------------------------------------------------------------------
command -v curl >/dev/null 2>&1 || die "curl is required to download cloudflared"

install_cloudflared

# Resolve web port (required).
if [[ -z "$WEB_PORT" ]]; then
  WEB_PORT="$(detect_port 4000 3000 || true)"
fi
[[ -n "$WEB_PORT" ]] || die "No web app is listening on :4000 or :3000. Start it first (make compose or make web-dev)."

# Resolve api port (optional convenience for the /docs link + direct API use).
if [[ "$TUNNEL_API" -eq 1 && -z "$API_PORT" ]]; then
  API_PORT="$(detect_port 3646 8000 || true)"
fi

PIDS=()
log "Starting Cloudflare quick tunnel for the web app on :$WEB_PORT ..."
start_tunnel web "$WEB_PORT" || die "Failed to start the web tunnel."
WEB_URL="$TUNNEL_URL"

API_URL=""
if [[ "$TUNNEL_API" -eq 1 && -n "$API_PORT" ]]; then
  log "Starting Cloudflare quick tunnel for the API on :$API_PORT ..."
  if start_tunnel api "$API_PORT"; then
    API_URL="$TUNNEL_URL"
  else
    warn "API tunnel failed; web sharing still works."
  fi
elif [[ "$TUNNEL_API" -eq 1 ]]; then
  warn "No API is listening on :3646 or :8000 - skipping the API tunnel."
fi

API_LINES=""
if [[ -n "$API_URL" ]]; then
  API_LINES=$(printf '   API     : %s\n   API docs: %s/docs' "$API_URL" "$API_URL")
fi

cat <<EOF

============================================================
 DeFiScope is live on a public Cloudflare URL

   Web app : $WEB_URL
${API_LINES:+$API_LINES
}
 Share the Web app link above. It works for anyone, anywhere.
 Quick tunnels are ephemeral - the URL changes on every run.

 NOTE: the in-app "API" (docs) link is baked at build time to a localhost
 address, so for external users open the API docs URL printed above directly.

 Press Ctrl+C to stop sharing.
============================================================

EOF

# Block until the WEB tunnel (our primary, PIDS[0]) exits. Waiting on the API
# child would let a transient API-tunnel crash tear down the healthy web share.
# When the web tunnel dies (crash or Ctrl+C via the traps above), cleanup kills
# the remaining children.
wait "${PIDS[0]}" || true
