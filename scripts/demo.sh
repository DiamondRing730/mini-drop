#!/usr/bin/env bash
# Bring the stack up and fire one py-spy task against the demo workload, end to end.
set -euo pipefail

BASE="${MINIDROP_BASE:-http://localhost:8000}"
WEB="${MINIDROP_WEB:-http://localhost:8080}"

echo "[demo] bringing up the stack (build if needed)..."
docker compose up -d --build

echo "[demo] waiting for server health..."
for _ in $(seq 1 90); do
  curl -fs "$BASE/healthz" >/dev/null 2>&1 && break || sleep 1
done

echo "[demo] waiting for an online agent..."
for _ in $(seq 1 60); do
  curl -fs "$BASE/api/v1/agents" 2>/dev/null | grep -q '"online":true' && break || sleep 1
done

echo "[demo] resolving demo workload host PID..."
PID=""
for _ in $(seq 1 30); do
  PID=$(docker inspect -f '{{.State.Pid}}' minidrop-workload 2>/dev/null || true)
  if [ -n "${PID:-}" ] && [ "$PID" != "0" ]; then break; fi
  sleep 1
done
if [ -z "${PID:-}" ] || [ "$PID" = "0" ]; then
  echo "[demo] ERROR: could not resolve the workload PID (is the workload container running?)" >&2
  exit 1
fi

echo "[demo] creating a py-spy task for host PID $PID ..."
curl -fs -X POST "$BASE/api/v1/tasks" \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"demo\",\"target_pid\":$PID,\"duration_sec\":10,\"frequency_hz\":99,\"profiler_type\":\"pyspy\"}"
echo

echo "[demo] task submitted. Open ${WEB} and watch it go PENDING -> RUNNING -> UPLOADING -> DONE,"
echo "[demo] then the flamegraph + TopN appear on the task detail page."
