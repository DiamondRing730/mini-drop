#!/usr/bin/env bash
# Run one selected workload, submit one profiling task, and wait for analysis.
set -euo pipefail

SCENARIO="${1:-cpu-before}"
BASE="${MINIDROP_BASE:-http://localhost:8000}"
WEB="${MINIDROP_WEB:-http://localhost:8080}"

case "$SCENARIO" in
  cpu-before)
    TASK_NAME="demo-cpu-before-baseline"; PROFILER="pyspy"; TARGET_MODE="pid"; DURATION=10 ;;
  cpu-after)
    TASK_NAME="demo-cpu-after-optimized"; PROFILER="pyspy"; TARGET_MODE="pid"; DURATION=10 ;;
  numeric)
    TASK_NAME="demo-numeric-loops"; PROFILER="pyspy"; TARGET_MODE="pid"; DURATION=10 ;;
  io)
    TASK_NAME="demo-io-syscalls"; PROFILER="ebpf"; TARGET_MODE="system"; DURATION=8 ;;
  *)
    echo "[demo] unknown scenario: $SCENARIO" >&2
    echo "[demo] choose: cpu-before | cpu-after | numeric | io" >&2
    exit 2
    ;;
esac

json_field() {
  python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$1"
}

if curl -fs "$BASE/healthz" >/dev/null 2>&1 \
  && curl -fs "$BASE/api/v1/agents" 2>/dev/null | grep -q '"online":true' \
  && curl -fs "$WEB" >/dev/null 2>&1; then
  echo "[demo] reusing the running Mini-Drop stack."
else
  echo "[demo] starting Mini-Drop services (build if needed)..."
  docker compose up -d --build postgres server agent analyzer web
fi

echo "[demo] starting only workload scenario: $SCENARIO"
MINIDROP_DEMO_SCENARIO="$SCENARIO" docker compose up -d --force-recreate workload

echo "[demo] waiting for server and agent..."
for _ in $(seq 1 90); do
  curl -fs "$BASE/healthz" >/dev/null 2>&1 && break || sleep 1
done
curl -fs "$BASE/healthz" >/dev/null || { echo "[demo] server did not become healthy" >&2; exit 1; }
for _ in $(seq 1 60); do
  curl -fs "$BASE/api/v1/agents" 2>/dev/null | grep -q '"online":true' && break || sleep 1
done
curl -fs "$BASE/api/v1/agents" | grep -q '"online":true' || { echo "[demo] no online agent" >&2; exit 1; }

PID=""
for _ in $(seq 1 30); do
  PID=$(docker inspect -f '{{.State.Pid}}' minidrop-workload 2>/dev/null || true)
  if [ -n "${PID:-}" ] && [ "$PID" != "0" ]; then break; fi
  sleep 1
done
if [ -z "${PID:-}" ] || [ "$PID" = "0" ]; then
  echo "[demo] could not resolve workload PID" >&2
  exit 1
fi

TARGET_PID="$PID"
if [ "$TARGET_MODE" = "system" ]; then TARGET_PID=0; fi
echo "[demo] submitting $TASK_NAME ($PROFILER, target=$TARGET_PID, workload pid=$PID)..."
RESPONSE=$(curl -fs -X POST "$BASE/api/v1/tasks" \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"$TASK_NAME\",\"target_pid\":$TARGET_PID,\"duration_sec\":$DURATION,\"frequency_hz\":99,\"profiler_type\":\"$PROFILER\"}")
TID=$(printf '%s' "$RESPONSE" | json_field tid)
if [ -z "$TID" ]; then
  echo "[demo] task submission returned no tid: $RESPONSE" >&2
  exit 1
fi

echo "[demo] task $TID submitted; waiting for collection and analysis..."
for _ in $(seq 1 90); do
  DETAIL=$(curl -fs "$BASE/api/v1/tasks/$TID")
  STATUS=$(printf '%s' "$DETAIL" | json_field status)
  ANALYSIS=$(printf '%s' "$DETAIL" | json_field analysis_status)
  if [ "$STATUS" = "FAILED" ] || [ "$ANALYSIS" = "FAILED" ]; then
    echo "[demo] task failed: $DETAIL" >&2
    exit 1
  fi
  if [ "$STATUS" = "DONE" ] && [ "$ANALYSIS" = "DONE" ]; then
    echo "[demo] complete: $WEB/#/task/$TID"
    if [ "$SCENARIO" = "cpu-before" ]; then
      echo "[demo] next: run 'make demo-after', then compare it against baseline $TID."
    elif [ "$SCENARIO" = "cpu-after" ]; then
      echo "[demo] select a demo-cpu-before-baseline task in the optimization panel."
    fi
    exit 0
  fi
  sleep 2
done

echo "[demo] timed out waiting for task $TID" >&2
exit 1
