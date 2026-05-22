# House Monitor — Home Assistant Add-on

Live dashboard for your Zehnder ComfoAir Q450 and Heatmiser Neostat system.

## What it shows

- **Zehnder MVHR** — supply/extract/outdoor temps, humidity, HRV efficiency %, fan duty %, filter life countdown
- **Heatmiser** — per-zone floor & air temps, set temps, heat on/off, call-for-heat status
- **Charts** — all sensors over 6h / 24h / 3d / 7d
- **Auto-refreshes** every 60 seconds

## Installation

1. In Home Assistant go to **Settings → Add-ons → Add-on Store**
2. Click the **⋮ menu** (top right) → **Repositories**
3. Add: `https://github.com/YOUR_GITHUB_USERNAME/ha-house-monitor`
4. Find **House Monitor** in the store and click **Install**
5. Configure your Heatmiser Neo Hub IP in the **Configuration** tab
6. Click **Start**

The dashboard opens via the **House Monitor** entry in your sidebar.

## Configuration

| Option | Default | Description |
|---|---|---|
| `heatmiser_ip` | `192.168.1.13` | IP address of your Heatmiser Neo Hub |
| `heatmiser_port` | `4242` | Neo Hub port (legacy API) |
| `poll_interval` | `60` | Seconds between polls |

The Zehnder data is pulled from Home Assistant automatically using the ComfoConnect integration — no extra config needed.

## Requirements

- Zehnder ComfoConnect integration installed and working in HA
- Heatmiser Neo Hub on your local network (legacy API mode, port 4242)
