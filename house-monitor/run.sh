#!/usr/bin/with-contenv bashio

# ── Read config from HA options ───────────────────────────────────────────────
export HEATMISER_IP=$(bashio::config 'heatmiser_ip')
export HEATMISER_PORT=$(bashio::config 'heatmiser_port')
export POLL_INTERVAL=$(bashio::config 'poll_interval')

# ── HA API token (injected automatically by Supervisor) ───────────────────────
export HA_TOKEN="${SUPERVISOR_TOKEN}"
export HA_URL="http://supervisor/core"

export DB_PATH="/data/monitor.db"

bashio::log.info "Starting House Monitor..."
bashio::log.info "Heatmiser: ${HEATMISER_IP}:${HEATMISER_PORT}"
bashio::log.info "Polling every ${POLL_INTERVAL}s"

# Start poller in background
python3 /app/poller.py &

# Start web server
python3 /app/app.py
