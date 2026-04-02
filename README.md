# ML Infrastructure Monitor

Real-time system metrics collector for Linux — built to monitor GPU training workloads. Collects CPU, RAM, disk, GPU, and network stats every 5 seconds, stores them in InfluxDB, and visualizes them on a live Grafana dashboard.

---

## Stack

| Component | Tech |
|---|---|
| Collector | Python 3, numpy |
| GPU stats | nvidia-smi |
| Database | InfluxDB v2 |
| Dashboard | Grafana |
| Service | systemd |
| Deployment | Docker Compose |

---

## Quick Start

**1. Clone and set up**
```bash
git clone https://github.com/<username>/ml-infra-monitor.git
cd ml-infra-monitor
bash scripts/setup.sh
```

**2. Add your InfluxDB token to `.env`**

Open InfluxDB at `http://localhost:8086`, go to Load Data → API Tokens, generate a token, and paste it into `.env`.

**3. Run the collector**
```bash
cd python_collector
python3 main_loop.py
```

**4. Open Grafana**

Go to `http://localhost:3000` (login: admin/admin), add InfluxDB as a data source, and import `grafana/dashboards/ml_monitor.json`.

---

## Run as systemd service

```bash
bash scripts/service.sh
journalctl -u collector -f
```

---

## Project Structure

```
ml-infra-monitor/
├── python_collector/
│   ├── main_loop.py        # daemon entry point
│   ├── data_collection.py  # reads /proc and nvidia-smi
│   ├── preprocessing.py    # delta computation + anomaly detection
│   ├── sending_to_db.py    # InfluxDB write functions
│   ├── config.py           # loads .env
│   └── requirements.txt
├── docker/
│   └── docker-compose.yml  # InfluxDB + Grafana
├── systemd/
│   └── collector.service
├── scripts/
│   ├── setup.sh
│   └── service.sh
├── grafana/
│   └── dashboards/
│       └── ml_monitor.json
├── .env.example
└── .gitignore
```

---

## Anomaly Detection

Each metric has a rolling window of 60 readings. A reading is flagged as an anomaly if it exceeds `mean + 2σ` of the window.

Bottleneck rules run every tick:
- CPU > 90% + GPU util < 60% → DataLoader bottleneck
- GPU memory growing monotonically → memory leak suspected
- Disk full in < 4 hours → critical alert
