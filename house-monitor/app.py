"""
app.py — Flask API server for the house monitor dashboard.
Serves static dashboard and JSON endpoints for chart data.
"""

import os
import sys
import time
import calendar
import sqlite3
import requests
from flask import Flask, jsonify, send_from_directory, request
from datetime import datetime, timedelta

DB_PATH       = os.environ.get("DB_PATH",       "/data/monitor.db")
HOUSE_NAME    = os.environ.get("HOUSE_NAME",    "House Monitor")
LATITUDE      = float(os.environ.get("LATITUDE",      "-45.03"))
LONGITUDE     = float(os.environ.get("LONGITUDE",     "168.66"))
HDD_BASE_TEMP = float(os.environ.get("HDD_BASE_TEMP", "18.0"))

_climate_cache = {"data": None, "ts": 0}

# Queenstown NZ monthly mean temperatures °C (NIWA 30-year climate normals).
# Used as a fallback when the Open-Meteo archive API is unreachable.
_QT_MONTHLY_MEANS = {
    1: 17.3, 2: 17.0, 3: 14.6, 4: 11.0, 5: 7.4, 6: 4.8,
    7: 4.3, 8: 6.2, 9: 9.0, 10: 11.5, 11: 13.8, 12: 16.0,
}


def _fallback_normals() -> dict:
    """Return {MM-DD: mean_temp} from static Queenstown NIWA monthly means."""
    result = {}
    for month, mean in _QT_MONTHLY_MEANS.items():
        _, n_days = calendar.monthrange(2000, month)
        for day in range(1, n_days + 1):
            result[f"{month:02d}-{day:02d}"] = mean
    return result


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


def fetch_climate_normals(days: int) -> dict:
    """Return {MM-DD: historical_mean_temp} from Open-Meteo archive, cached 24h.
    Falls back to static Queenstown NIWA monthly means if the API is unreachable.
    Failures are cached for 30 min to avoid hammering the API on every request."""
    global _climate_cache
    age = time.time() - _climate_cache["ts"]
    if _climate_cache["ts"] > 0:
        ttl = 86400 if _climate_cache["data"] else 1800
        if age < ttl:
            return _climate_cache["data"] if _climate_cache["data"] else _fallback_normals()
    try:
        today = datetime.utcnow().date()
        # Fetch a window wider than requested — archive lags ~5 days so end 6 days ago
        end_hist   = today.replace(year=today.year - 1) - timedelta(days=6)
        start_hist = end_hist - timedelta(days=days + 14)
        r = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude":   LATITUDE,
                "longitude":  LONGITUDE,
                "start_date": start_hist.isoformat(),
                "end_date":   end_hist.isoformat(),
                "daily":      "temperature_2m_mean",
                "timezone":   "UTC",
            },
            timeout=10,
        )
        r.raise_for_status()
        daily = r.json().get("daily", {})
        normals = {
            t[5:]: temp
            for t, temp in zip(daily.get("time", []), daily.get("temperature_2m_mean", []))
            if temp is not None
        }
        print(f"[house-monitor] Open-Meteo: fetched {len(normals)} days of historical temps ({start_hist} to {end_hist})", file=sys.stderr)
        _climate_cache = {"data": normals, "ts": time.time()}
        return normals
    except Exception as e:
        print(f"[house-monitor] Open-Meteo fetch failed: {e}. Using static Queenstown climate normals.", file=sys.stderr)
        _climate_cache = {"data": None, "ts": time.time()}
        return _fallback_normals()


@app.get("/api/hdd")
def api_hdd():
    days = int(request.args.get("days", 30))
    conn = get_db()
    rows = conn.execute("""
        SELECT day, ROUND(MAX(0.0, ? - avg_temp), 2) AS actual_hdd,
               ROUND(avg_temp, 1) AS avg_outdoor
        FROM (
            SELECT date(ts) AS day, AVG(outdoor_temp) AS avg_temp
            FROM zehnder
            WHERE ts >= date('now', ?) AND date(ts) < date('now')
            GROUP BY date(ts)
        )
        ORDER BY day ASC
    """, (HDD_BASE_TEMP, f"-{days} days")).fetchall()

    result = [dict(r) for r in rows]

    normals = fetch_climate_normals(days)
    for row in result:
        md = row["day"][5:]  # "MM-DD"
        hist = normals.get(md)
        row["historical_hdd"] = round(max(0.0, HDD_BASE_TEMP - hist), 2) if hist is not None else None

    return jsonify(result)


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
