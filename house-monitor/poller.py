"""
poller.py — Polls Home Assistant REST API for Zehnder and Heatmiser data,
stores readings to SQLite every POLL_INTERVAL seconds.
"""

import os
import time
import sqlite3
import logging
import requests
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
HA_URL             = os.environ.get("HA_URL",             "http://homeassistant.local:8123").rstrip("/")
HA_TOKEN           = os.environ.get("HA_TOKEN",           "")
HEATMISER_IP       = os.environ.get("HEATMISER_IP",       "192.168.1.13")
HEATMISER_PORT     = int(os.environ.get("HEATMISER_PORT", "4242"))
POLL_INTERVAL      = int(os.environ.get("POLL_INTERVAL",  "60"))
DB_PATH            = os.environ.get("DB_PATH",            "/data/monitor.db")
ZEHNDER_DEVICE_ID  = os.environ.get("ZEHNDER_DEVICE_ID",  "comfoairq_stockyard")
ZEHNDER_FAN_ENTITY = os.environ.get("ZEHNDER_FAN_ENTITY", "fan.comfoairq")
TANK_DEVICE_ID     = os.environ.get("TANK_DEVICE_ID",     "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

# ── Entity ID maps — built from config at startup ─────────────────────────────
def build_zehnder_entities(device_id: str, fan_entity: str) -> dict:
    return {
        "supply_temp":      f"sensor.{device_id}_supply_temperature",
        "extract_temp":     f"sensor.{device_id}_inside_temperature",
        "exhaust_temp":     f"sensor.{device_id}_exhaust_temperature",
        "outdoor_temp":     f"sensor.{device_id}_outside_temperature",
        "supply_humidity":  f"sensor.{device_id}_supply_humidity",
        "extract_humidity": f"sensor.{device_id}_inside_humidity",
        "exhaust_humidity": f"sensor.{device_id}_exhaust_humidity",
        "outdoor_humidity": f"sensor.{device_id}_outside_humidity",
        "bypass_state":     f"sensor.{device_id}_bypass_state",
        "operating_mode":   f"select.{device_id}_ventilation_mode",
        "fan_entity":       fan_entity,
        "filter_days":      f"sensor.{device_id}_days_to_replace_filter",
    }


def build_tank_entities(device_id: str) -> dict:
    return {
        "current_volume":  f"sensor.{device_id}_current_volume_tankmate",
        "percent_full":    f"sensor.{device_id}_percent_full_tankmate",
        "water_height":    f"sensor.{device_id}_water_height",
        "battery_voltage": f"sensor.{device_id}_battery_voltage",
    }

# ── Database setup ─────────────────────────────────────────────────────────────
def init_db(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS zehnder (
            ts                  TEXT PRIMARY KEY,
            supply_temp         REAL,
            extract_temp        REAL,
            exhaust_temp        REAL,
            outdoor_temp        REAL,
            supply_humidity     REAL,
            extract_humidity    REAL,
            supply_fan_rpm      INTEGER,
            extract_fan_rpm     INTEGER,
            supply_fan_pct      INTEGER,
            extract_fan_pct     INTEGER,
            bypass_state        TEXT,
            operating_mode      TEXT,
            efficiency          REAL,
            filter_days         INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS heatmiser (
            ts              TEXT,
            thermostat      TEXT,
            floor_temp      REAL,
            air_temp        REAL,
            set_temp        REAL,
            heating_on      INTEGER,
            PRIMARY KEY (ts, thermostat)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS heatmiser_avg (
            ts              TEXT PRIMARY KEY,
            avg_floor_temp  REAL,
            avg_air_temp    REAL,
            call_for_heat   INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tank (
            ts              TEXT PRIMARY KEY,
            current_volume  REAL,
            percent_full    REAL,
            water_height    REAL,
            battery_voltage REAL
        )
    """)

    # ── Auto-migrate: add any missing columns ─────────────────────────────────
    migrations = [
        ("zehnder",       "efficiency",    "ALTER TABLE zehnder ADD COLUMN efficiency REAL"),
        ("zehnder",       "filter_days",   "ALTER TABLE zehnder ADD COLUMN filter_days INTEGER"),
        ("heatmiser_avg", "call_for_heat", "ALTER TABLE heatmiser_avg ADD COLUMN call_for_heat INTEGER"),
    ]
    existing = {}
    for table, col, sql in migrations:
        if table not in existing:
            existing[table] = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if col not in existing[table]:
            conn.execute(sql)
            log.info(f"DB migration: added {table}.{col}")
            existing[table].add(col)

    conn.commit()
    return conn


# ── HA helpers ─────────────────────────────────────────────────────────────────
def get_all_states() -> list[dict]:
    r = requests.get(f"{HA_URL}/api/states", headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def get_state(entity_id: str) -> str | None:
    try:
        r = requests.get(f"{HA_URL}/api/states/{entity_id}", headers=HEADERS, timeout=5)
        if r.status_code == 200:
            return r.json().get("state")
    except Exception:
        pass
    return None


def safe_float(val) -> float | None:
    try:
        f = float(val)
        return None if f in (float('inf'), float('-inf')) else f
    except (TypeError, ValueError):
        return None


# ── Entity discovery ───────────────────────────────────────────────────────────
def discover_entities(states: list[dict]) -> dict:
    return build_zehnder_entities(ZEHNDER_DEVICE_ID, ZEHNDER_FAN_ENTITY)


def log_discovered(entity_map: dict):
    log.info("=== Discovered entities ===")
    for k, v in entity_map.items():
        log.info(f"  {k:25s} → {v}")
    log.info("===========================")


# ── Zehnder polling ────────────────────────────────────────────────────────────
def poll_zehnder(entity_map: dict, states_by_id: dict) -> dict | None:
    try:
        def val(field):
            eid = entity_map.get(field)
            if not eid:
                return None
            s = states_by_id.get(eid, {}).get("state")
            return safe_float(s) if s not in (None, "unavailable", "unknown") else None

        def text_val(field):
            eid = entity_map.get(field)
            if not eid:
                return None
            s = states_by_id.get(eid, {}).get("state")
            return s if s not in (None, "unavailable", "unknown") else None

        # Fan speed comes from fan entity attributes
        fan_state  = states_by_id.get(entity_map.get("fan_entity", ""), {})
        fan_attrs  = fan_state.get("attributes", {})
        fan_pct    = safe_float(fan_attrs.get("percentage"))

        result = {
            "supply_temp":      val("supply_temp"),
            "extract_temp":     val("extract_temp"),
            "exhaust_temp":     val("exhaust_temp"),
            "outdoor_temp":     val("outdoor_temp"),
            "supply_humidity":  val("supply_humidity"),
            "extract_humidity": val("extract_humidity"),
            "supply_fan_rpm":   None,
            "extract_fan_rpm":  None,
            "supply_fan_pct":   fan_pct,
            "extract_fan_pct":  fan_pct,
            "bypass_state":     text_val("bypass_state"),
            "operating_mode":   text_val("operating_mode"),
        }

        # Heat recovery efficiency: (supply - outdoor) / (extract - outdoor) * 100
        efficiency = None
        if result["supply_temp"] is not None and result["outdoor_temp"] is not None and result["extract_temp"] is not None:
            denom = result["extract_temp"] - result["outdoor_temp"]
            if denom > 0.5:  # avoid division by near-zero in mild weather
                efficiency = round((result["supply_temp"] - result["outdoor_temp"]) / denom * 100, 1)

        result["efficiency"]  = efficiency
        result["filter_days"] = val("filter_days")

        numeric = [v for k, v in result.items() if k not in ("bypass_state", "operating_mode", "supply_fan_rpm", "extract_fan_rpm", "efficiency", "filter_days") and v is not None]
        if not numeric:
            log.warning("Zehnder: no numeric values found")
            return None

        return result
    except Exception as e:
        log.error(f"Zehnder poll error: {e}")
        return None


# ── Heatmiser polling ──────────────────────────────────────────────────────────
# ── Heatmiser polling (direct legacy JSON socket — no auth required) ──────────
def poll_heatmiser() -> tuple[list[dict], dict | None]:
    """
    Poll all Neostats via Neo Hub legacy JSON API on port 4242.
    Uses GET_LIVE_DATA command — no PIN or authentication required.
    """
    import socket, json

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            s.connect((HEATMISER_IP, HEATMISER_PORT))
            cmd = json.dumps({"GET_LIVE_DATA": "GET_LIVE_DATA"}) + "\x00"
            s.sendall(cmd.encode("utf-8"))
            buf = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b"\x00" in buf:
                    break

        payload = buf.rstrip(b"\x00").decode("utf-8")
        data = json.loads(payload)
        devices = data.get("devices", [])

        rows        = []
        floor_temps = []
        air_temps   = []
        active      = 0

        for dev in devices:
            if not isinstance(dev, dict):
                continue
            if not dev.get("THERMOSTAT", False):
                continue

            name       = dev.get("ZONE_NAME", f"Zone {dev.get('DEVICE_ID', '?')}")
            air_temp   = float(dev["ACTUAL_TEMP"])           if dev.get("ACTUAL_TEMP")                   is not None else None
            floor_temp = float(dev["CURRENT_FLOOR_TEMPERATURE"]) if dev.get("CURRENT_FLOOR_TEMPERATURE") is not None else None
            set_temp   = float(dev["SET_TEMP"])              if dev.get("SET_TEMP")                      is not None else None
            heating_on = 1 if dev.get("HEAT_ON") else 0

            rows.append({
                "thermostat": name,
                "floor_temp": floor_temp,
                "air_temp":   air_temp,
                "set_temp":   set_temp,
                "heating_on": heating_on,
            })

            if floor_temp is not None: floor_temps.append(floor_temp)
            if air_temp   is not None: air_temps.append(air_temp)
            if heating_on: active += 1

        if not rows:
            log.warning("Heatmiser: no thermostat devices in response")
            return [], None

        # Living Room is the master stat — its HEAT_ON = call for heat signal to the heat pump
        call_for_heat = 0
        for dev in devices:
            if isinstance(dev, dict) and dev.get("THERMOSTAT") and dev.get("ZONE_NAME") == "Living Room":
                call_for_heat = 1 if dev.get("HEAT_ON") else 0
                break

        avg = {
            "avg_floor_temp": round(sum(floor_temps) / len(floor_temps), 2) if floor_temps else None,
            "avg_air_temp":   round(sum(air_temps)   / len(air_temps),   2) if air_temps   else None,
            "call_for_heat":  call_for_heat,
        }

        return rows, avg

    except Exception as e:
        log.error(f"Heatmiser poll failed: {e}")
        return [], None


# ── Tank polling ──────────────────────────────────────────────────────────────
def poll_tank(states_by_id: dict) -> dict | None:
    if not TANK_DEVICE_ID:
        return None
    try:
        entities = build_tank_entities(TANK_DEVICE_ID)

        def val(entity_id):
            s = states_by_id.get(entity_id, {}).get("state")
            return safe_float(s) if s not in (None, "unavailable", "unknown") else None

        result = {
            "current_volume":  val(entities["current_volume"]),
            "percent_full":    val(entities["percent_full"]),
            "water_height":    val(entities["water_height"]),
            "battery_voltage": val(entities["battery_voltage"]),
        }

        if result["current_volume"] is None and result["percent_full"] is None:
            log.warning("Tank: no data available — check tank_device_id in config")
            return None

        return result
    except Exception as e:
        log.error(f"Tank poll error: {e}")
        return None


# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    conn = init_db(DB_PATH)
    log.info(f"House Monitor starting — HA at {HA_URL} — polling every {POLL_INTERVAL}s")

    # Discover entities once at startup
    log.info("Discovering HA entities...")
    try:
        states = get_all_states()
        entity_map = discover_entities(states)
        log_discovered(entity_map)
    except Exception as e:
        log.error(f"Could not reach Home Assistant: {e}")
        log.error("Check HA_URL and HA_TOKEN in docker-compose.yml")
        raise

    while True:
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        try:
            states = get_all_states()
            states_by_id = {s["entity_id"]: s for s in states}
        except Exception as e:
            log.error(f"Failed to fetch HA states: {e}")
            time.sleep(POLL_INTERVAL)
            continue

        # Zehnder
        z = poll_zehnder(entity_map, states_by_id)
        if z:
            conn.execute("""
                INSERT OR REPLACE INTO zehnder VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ts,
                z["supply_temp"],    z["extract_temp"],
                z["exhaust_temp"],   z["outdoor_temp"],
                z["supply_humidity"],z["extract_humidity"],
                z["supply_fan_rpm"], z["extract_fan_rpm"],
                z["supply_fan_pct"], z["extract_fan_pct"],
                z["bypass_state"],   z["operating_mode"],
                z["efficiency"],     z["filter_days"],
            ))
            log.info(
                f"Zehnder ✓  supply={z['supply_temp']}°C  "
                f"outdoor={z['outdoor_temp']}°C  "
                f"efficiency={z['efficiency']}%  "
                f"extract_RH={z['extract_humidity']}%  "
                f"fans {z['supply_fan_pct']}%  "
                f"filter={z['filter_days']}d"
            )
        
        # Heatmiser — direct socket poll
        rows, avg = poll_heatmiser()
        for r in rows:
            conn.execute("""
                INSERT OR REPLACE INTO heatmiser VALUES (?,?,?,?,?,?)
            """, (ts, r["thermostat"], r["floor_temp"], r["air_temp"], r["set_temp"], r["heating_on"]))

        if avg:
            conn.execute("""
                INSERT OR REPLACE INTO heatmiser_avg VALUES (?,?,?,?)
            """, (ts, avg["avg_floor_temp"], avg["avg_air_temp"], avg["call_for_heat"]))
            log.info(
                f"Heatmiser ✓  avg_floor={avg['avg_floor_temp']}°C  "
                f"avg_air={avg['avg_air_temp']}°C  "
                f"call_for_heat={'YES' if avg['call_for_heat'] else 'NO'}"
            )

        # Tank
        t = poll_tank(states_by_id)
        if t:
            conn.execute("""
                INSERT OR REPLACE INTO tank VALUES (?,?,?,?,?)
            """, (ts, t["current_volume"], t["percent_full"], t["water_height"], t["battery_voltage"]))
            log.info(
                f"Tank ✓  volume={t['current_volume']}L  "
                f"full={t['percent_full']}%  "
                f"height={t['water_height']}m  "
                f"batt={t['battery_voltage']}V"
            )

        conn.commit()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
