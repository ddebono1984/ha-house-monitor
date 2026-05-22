# House Monitor — Home Assistant Add-on

Live dashboard for your Zehnder ComfoAir Q, Heatmiser Neostat and TankMate water tank sensor.

## What it shows

- **Zehnder MVHR** — supply/extract/outdoor temps, humidity, HRV efficiency %, fan duty %, filter life countdown
- **Heatmiser** — per-zone floor & air temps, set temps, heat on/off, call-for-heat status
- **TankMate** — water tank level %, current volume (L), water height, sensor battery voltage
- **Charts** — all sensors over 6h / 24h / 3d / 7d
- **Alerts** — low tank warning (< 20%), filter replacement warning (< 30 days)
- **Auto-refreshes** every 60 seconds

## Installation

1. In Home Assistant go to **Settings → Add-ons → Add-on Store**
2. Click the **⋮ menu** (top right) → **Repositories**
3. Add: `https://github.com/ddebono1984/ha-house-monitor`
4. Find **House Monitor** in the store and click **Install**
5. Fill in the **Configuration** tab (see below)
6. Click **Start**

The dashboard opens via the **House Monitor** entry in your sidebar.

## Configuration

| Option | Default | Description |
|---|---|---|
| `house_name` | `My Home` | Display name shown in the dashboard header |
| `heatmiser_ip` | `192.168.1.13` | IP address of your Heatmiser Neo Hub |
| `heatmiser_port` | `4242` | Neo Hub port (legacy API) |
| `poll_interval` | `60` | Seconds between polls |
| `zehnder_device_id` | `comfoairq_stockyard` | Device ID prefix used by the ComfoConnect integration in HA — find it in Developer Tools → States by searching for your supply temperature entity (e.g. `sensor.comfoairq_XXXX_supply_temperature` → set this to `comfoairq_XXXX`) |
| `zehnder_fan_entity` | `fan.comfoairq` | Entity ID of the ComfoAir fan entity in HA |
| `tank_device_id` | `stockyard_tanks` | Device ID prefix for your TankMate sensor in HA — find it in Developer Tools → States by searching for your tank (e.g. `sensor.XXXX_percent_full_tankmate` → set this to `XXXX`). Leave blank if you don't have a TankMate. |

## Requirements

- Zehnder ComfoConnect integration installed and working in HA
- Heatmiser Neo Hub on your local network (legacy API mode, port 4242)
- TankMate sensor integrated into HA *(optional)*
