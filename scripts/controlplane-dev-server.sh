#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)

PID_DIR="$ROOT_DIR/.aquarium/run"
LOG_DIR="$ROOT_DIR/.aquarium/logs"
PID_FILE="$PID_DIR/controlplane.pid"
LOG_FILE="$LOG_DIR/controlplane.log"

is_responding() {
  curl -fsS http://127.0.0.1:15000/admin/login/ >/dev/null 2>&1
}

is_running() {
  [ -f "$PID_FILE" ] || return 1
  PID=$(cat "$PID_FILE")
  [ -n "$PID" ] || return 1
  kill -0 "$PID" 2>/dev/null
}

start_server() {
  mkdir -p "$PID_DIR" "$LOG_DIR"
  if is_running; then
    echo "controlplane already running with pid $(cat "$PID_FILE")"
    exit 0
  fi
  if is_responding; then
    echo "controlplane already responding on http://127.0.0.1:15000/admin/"
    exit 0
  fi
  rm -f "$PID_FILE"
  cd "$ROOT_DIR"
  nohup .venv/bin/python manage.py runserver 127.0.0.1:15000 --noreload >"$LOG_FILE" 2>&1 &
  PID=$!
  echo "$PID" >"$PID_FILE"
  sleep 1
  if ! kill -0 "$PID" 2>/dev/null && ! is_responding; then
    echo "controlplane failed to start; check $LOG_FILE" >&2
    exit 1
  fi
  if kill -0 "$PID" 2>/dev/null; then
    echo "controlplane started on http://127.0.0.1:15000/admin/ (pid $PID)"
  else
    rm -f "$PID_FILE"
    echo "controlplane already responding on http://127.0.0.1:15000/admin/"
  fi
}

stop_server() {
  if ! is_running; then
    rm -f "$PID_FILE"
    if is_responding; then
      echo "controlplane is running, but not under the local helper"
      exit 0
    fi
    echo "controlplane is not running"
    exit 0
  fi
  PID=$(cat "$PID_FILE")
  kill "$PID"
  rm -f "$PID_FILE"
  echo "controlplane stopped"
}

status_server() {
  if is_running; then
    echo "controlplane running with pid $(cat "$PID_FILE")"
  elif is_responding; then
    echo "controlplane responding on http://127.0.0.1:15000/admin/ (external process)"
  else
    echo "controlplane not running" >&2
    exit 1
  fi
}

case "${1:-}" in
  start)
    start_server
    ;;
  stop)
    stop_server
    ;;
  status)
    status_server
    ;;
  *)
    echo "usage: $0 {start|stop|status}" >&2
    exit 64
    ;;
esac
