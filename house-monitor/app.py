"""
app.py — Flask API server for the house monitor dashboard.
Serves static dashboard and JSON endpoints for chart data.
"""

import os
import sqlite3
from flask import Flask, jsonify, send_from_directory, request

DB_PATH = os.environ.get("DB_PATH", "/data/monitor.db")

app = Flask(__name__, static_folder="static")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hours_ago(h: int) -> str:
    from datetime import datetime, timedelta
    return (datetime.utcnow() - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S")


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/zehnder")
def api_zehnder():
    hours = int(request.args.get("hours", 24))
    conn = get_db()
    rows = conn.execute("""
        SELECT ts, supply_temp, extract_temp, exhaust_temp, outdoor_temp,
               supply_humidity, extract_humidity,
               supply_fan_rpm, extract_fan_rpm,
               supply_fan_pct, extract_fan_pct,
               bypass_state, operating_mode,
               efficiency, filter_days
        FROM zehnder
        WHERE ts >= ?
        ORDER BY ts ASC
    """, (hours_ago(hours),)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/heatmiser/avg")
def api_heatmiser_avg():
    hours = int(request.args.get("hours", 24))
    conn = get_db()
    rows = conn.execute("""
        SELECT ts, avg_floor_temp, avg_air_temp, call_for_heat
        FROM heatmiser_avg
        WHERE ts >= ?
        ORDER BY ts ASC
    """, (hours_ago(hours),)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/heatmiser/zones")
def api_heatmiser_zones():
    """Latest reading per thermostat."""
    conn = get_db()
    rows = conn.execute("""
        SELECT h.thermostat, h.floor_temp, h.air_temp, h.set_temp, h.heating_on, h.ts
        FROM heatmiser h
        INNER JOIN (
            SELECT thermostat, MAX(ts) AS max_ts FROM heatmiser GROUP BY thermostat
        ) latest ON h.thermostat = latest.thermostat AND h.ts = latest.max_ts
        ORDER BY h.thermostat
    """).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/latest")
def api_latest():
    """Single combined snapshot for the live-reading cards."""
    conn = get_db()

    z = conn.execute(
        "SELECT * FROM zehnder ORDER BY ts DESC LIMIT 1"
    ).fetchone()

    h = conn.execute(
        "SELECT * FROM heatmiser_avg ORDER BY ts DESC LIMIT 1"
    ).fetchone()

    return jsonify({
        "zehnder":   dict(z) if z else None,
        "heatmiser": dict(h) if h else None,
    })


# ── Dashboard HTML ────────────────────────────────────────────────────────────

@app.get("/")
def dashboard():
    return send_from_directory("static", "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
