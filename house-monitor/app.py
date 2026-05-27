"""
app.py — Flask API server for the house monitor dashboard.
Serves static dashboard and JSON endpoints for chart data.
"""

import os
import sqlite3
from flask import Flask, jsonify, send_from_directory, request

DB_PATH    = os.environ.get("DB_PATH",     "/data/monitor.db")
HOUSE_NAME = os.environ.get("HOUSE_NAME", "House Monitor")

app = Flask(__name__, static_folder="static")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hours_ago(h: int) -> str:
    from datetime import datetime, timedelta
    return (datetime.utcnow() - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S")


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/config")
def api_config():
    return jsonify({"house_name": HOUSE_NAME})


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


@app.get("/api/thermal")
def api_thermal():
    hours = int(request.args.get("hours", 24))
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT
                z.ts,
                ROUND(h.avg_floor_temp - h.avg_air_temp,    2) AS floor_air_delta,
                ROUND(h.avg_air_temp   - z.outdoor_temp,    2) AS outdoor_drive,
                ROUND(h.avg_floor_temp - z.outdoor_temp,    2) AS slab_outdoor_delta
            FROM zehnder z
            INNER JOIN heatmiser_avg h ON z.ts = h.ts
            WHERE z.ts >= ?
            ORDER BY z.ts ASC
        """, (hours_ago(hours),)).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception:
        return jsonify([])


@app.get("/api/tank")
def api_tank():
    hours = int(request.args.get("hours", 24))
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT ts, current_volume, percent_full, water_height, battery_voltage
            FROM tank
            WHERE ts >= ?
            ORDER BY ts ASC
        """, (hours_ago(hours),)).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception:
        return jsonify([])


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

    t = None
    try:
        t = conn.execute(
            "SELECT * FROM tank ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    except Exception:
        pass

    return jsonify({
        "zehnder":   dict(z) if z else None,
        "heatmiser": dict(h) if h else None,
        "tank":      dict(t) if t else None,
    })


# ── Dashboard HTML ────────────────────────────────────────────────────────────

@app.get("/")
def dashboard():
    return send_from_directory("static", "index.html")

@app.get("/kiosk")
def kiosk():
    return send_from_directory("static", "kiosk.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
