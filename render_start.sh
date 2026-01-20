#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PERSIST_BASE="${PERSIST_BASE:-/var/data}"

log() { echo "[start] $*"; }

link_dir() {
  local src="$1"
  local dst="$2"

  mkdir -p "$dst"

  # Already linked
  if [ -L "$src" ]; then
    return 0
  fi

  if [ -d "$src" ]; then
    if [ -z "$(ls -A "$dst" 2>/dev/null || true)" ]; then
      log "Seeding $dst from $src"
      cp -a "$src"/. "$dst"/ 2>/dev/null || true
    else
      # Keep disk as source of truth; merge only missing defaults
      cp -an "$src"/. "$dst"/ 2>/dev/null || true
    fi

    rm -rf "$src"
    ln -s "$dst" "$src"
  else
    mkdir -p "$(dirname "$src")"
    ln -s "$dst" "$src"
  fi
}

if [ -d "$PERSIST_BASE" ] && [ -w "$PERSIST_BASE" ]; then
  log "Persistent disk detected at $PERSIST_BASE"
  link_dir "$APP_ROOT/data" "$PERSIST_BASE/data"
  link_dir "$APP_ROOT/static/uploads" "$PERSIST_BASE/uploads"
  link_dir "$APP_ROOT/static/cards" "$PERSIST_BASE/cards"
  link_dir "$APP_ROOT/digital_goods" "$PERSIST_BASE/digital_goods"
  chmod -R ug+rwX "$PERSIST_BASE" 2>/dev/null || true
else
  log "No writable persistent disk at $PERSIST_BASE (ephemeral filesystem)"
fi

PORT_TO_BIND="${PORT:-5050}"
log "Starting gunicorn on 0.0.0.0:${PORT_TO_BIND}"
exec gunicorn -b "0.0.0.0:${PORT_TO_BIND}" --workers "${WEB_CONCURRENCY:-2}" --threads "${GUNICORN_THREADS:-2}" --timeout "${GUNICORN_TIMEOUT:-120}" app:app
