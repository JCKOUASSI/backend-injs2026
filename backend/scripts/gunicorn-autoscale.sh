#!/usr/bin/env bash
# Démarre Gunicorn et ajuste le nombre de workers selon la charge (TTIN / TTOU).
set -o errexit

MIN="${GUNICORN_WORKERS_MIN:-2}"
MAX="${GUNICORN_WORKERS_MAX:-10}"
INTERVAL="${GUNICORN_AUTOSCALE_INTERVAL:-30}"
LOAD_UP="${GUNICORN_AUTOSCALE_LOAD_UP:-0.8}"
LOAD_DOWN="${GUNICORN_AUTOSCALE_LOAD_DOWN:-0.3}"
WORKERS="${GUNICORN_WORKERS:-auto}"

if [[ "$WORKERS" == "auto" ]]; then
  cpus=$(nproc 2>/dev/null || echo 2)
  WORKERS=$((2 * cpus + 1))
  if (( WORKERS < MIN )); then WORKERS=$MIN; fi
  if (( WORKERS > MAX )); then WORKERS=$MAX; fi
fi

echo "gunicorn: démarrage avec ${WORKERS} worker(s), autoscale ${MIN}-${MAX} (intervalle ${INTERVAL}s)"

gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "$WORKERS" \
  --timeout 120 \
  --access-logfile - &
MASTER_PID=$!

count_workers() {
  pgrep -P "$MASTER_PID" 2>/dev/null | wc -l | tr -d ' '
}

autoscale_loop() {
  local cpus load workers threshold_up threshold_down
  cpus=$(nproc 2>/dev/null || echo 2)
  sleep "$INTERVAL"
  while kill -0 "$MASTER_PID" 2>/dev/null; do
    if [[ -f /proc/loadavg ]]; then
      load=$(awk '{print $1}' /proc/loadavg)
      workers=$(count_workers)
      threshold_up=$(awk -v c="$cpus" -v r="$LOAD_UP" 'BEGIN{printf "%.2f", c*r}')
      threshold_down=$(awk -v c="$cpus" -v r="$LOAD_DOWN" 'BEGIN{printf "%.2f", c*r}')
      if awk -v l="$load" -v t="$threshold_up" 'BEGIN{exit !(l>t)}' && (( workers < MAX )); then
        echo "gunicorn autoscale: load=${load} > ${threshold_up} → +1 worker (${workers}/${MAX})"
        kill -TTIN "$MASTER_PID" 2>/dev/null || true
      elif awk -v l="$load" -v t="$threshold_down" 'BEGIN{exit !(l<t)}' && (( workers > MIN )); then
        echo "gunicorn autoscale: load=${load} < ${threshold_down} → -1 worker (${workers}/${MIN})"
        kill -TTOU "$MASTER_PID" 2>/dev/null || true
      fi
    fi
    sleep "$INTERVAL"
  done
}

if [[ "${GUNICORN_AUTOSCALE:-true}" == "true" ]]; then
  autoscale_loop &
fi

wait "$MASTER_PID"
