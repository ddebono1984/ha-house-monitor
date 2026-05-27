#!/usr/bin/with-contenv bashio

# ── Read config from HA options ───────────────────────────────────────────────
export HOUSE_NAME=$(bashio::config 'house_name')
export HEATMISER_IP=$(bashio::config 'heatmiser_ip')
export HEATMISER_PORT=$(bashio::config 'heatmiser_port')
export POLL_INTERVAL=$(bashio::config 'poll_interval')
export ZEHNDER_DEVICE_ID=$(bashio::config 'zehnder_device_id')
export ZEHNDER_FAN_ENTITY=$(bashio::config 'zehnder_fan_entity')
export TANK_DEVICE_ID=$(bashio::config 'tank_device_id' 2>/dev/null || echo "")
export LATITUDE=$(bashio::config 'latitude')
export LONGITUDE=$(bashio::config 'longitude')
export HDD_BASE_TEMP=$(bashio::config 'hdd_base_temp')

# ── HA API token (injected automatically by Supervisor) ───────────────────────
export HA_TOKEN="${SUPERVISOR_TOKEN}"
export HA_URL="http://supervisor/core"

export DB_PATH="/data/monitor.db"

bashio::log.info "Starting House Monitor..."
bashio::log.info "House: ${HOUSE_NAME}"
bashio::log.info "Heatmiser: ${HEATMISER_IP}:${HEATMISER_PORT}"
bashio::log.info "Zehnder device: ${ZEHNDER_DEVICE_ID}"
bashio::log.info "Polling every ${POLL_INTERVAL}s"

# Start poller in background
python3 /app/poller.py &

# Start web server
python3 /app/app.py
