# Architecture

## Overview

A real-time ML infrastructure monitor that collects system metrics every 5 seconds, detects anomalies using both statistical rules and a trained ML model, stores everything in InfluxDB, and visualizes it on a live Grafana dashboard.

Built as a Linux Systems & Administration project at IIT Jammu. Designed around monitoring GPU training workloads (NTIRE 2026 CVPR challenge, RTX A4000 / RTX 4060).

---

## System Diagram

```
+---------------------------+
|      Linux Kernel         |
|  /proc/stat               |  CPU tick counters
|  /proc/meminfo            |  Memory breakdown
|  /proc/diskstats          |  Disk sector counters
|  /proc/net/dev            |  Network byte counters
+------------+--------------+
             |
             |  (read directly, no libraries)
             v
+---------------------------+
|    nvidia-smi             |  GPU util, memory, temp, power
+------------+--------------+
             |
             v
+------------------------------------------+
|          python_collector/               |
|                                          |
|  data_collection.py                      |
|    - read_cpu()        raw tick counts   |
|    - read_memory()     raw kB values     |
|    - read_disk_usage() df -B1            |
|    - read_disk_io()    raw sector counts |
|    - read_gpu()        nvidia-smi call   |
|    - read_network()    raw byte counts   |
|                                          |
|  preprocessing.py                        |
|    - compute_cpu_percent()  delta math   |
|    - compute_disk_io()      delta + rate |
|    - compute_network_io()   delta + rate |
|    - AnomalyDetector        rolling 2sig |
|    - detect_bottlenecks()   rule-based   |
|    - predict_disk_full()    projection   |
|                                          |
|  anomaly_model.py                        |
|    - Isolation Forest inference          |
|    - trained on real baseline data       |
|                                          |
|  sending_to_db.py                        |
|    - one send_* function per measurement |
|    - lazy InfluxDB client init           |
|                                          |
|  main_loop.py     <-- entry point        |
|    - 5s tick loop                        |
|    - collect -> preprocess -> detect     |
|      -> infer -> send                    |
+------------------------------------------+
             |
             |  HTTP writes (influxdb-client)
             v
+---------------------------+
|   InfluxDB 2.7            |
|   bucket: ml_metrics      |
|   retention: 30 days      |
|                           |
|   measurements:           |
|     cpu_usage             |
|     memory                |
|     disk_usage            |
|     disk_io               |
|     gpu                   |
|     network               |
|     bottleneck_flags      |
|     ml_anomaly            |
|     training_run          |
+------------+--------------+
             |
             |  Flux queries
             v
+---------------------------+
|   Grafana                 |
|   auto-refresh: 5s        |
|                           |
|   panels:                 |
|     stat: CPU/RAM/GPU/temp |
|     timeseries: all above  |
|     table: anomalies       |
|     table: bottlenecks     |
|     annotations: run tags  |
+---------------------------+
```

---

## Deployment

```
+-----------------------------+
|  Docker Compose             |
|  +-------------------------+|
|  |  influxdb:2.7           ||  port 8086
|  |  volume: influxdb-data  ||
|  +-------------------------+|
|  +-------------------------+|
|  |  grafana:latest         ||  port 3000
|  |  volume: grafana-data   ||
|  +-------------------------+|
+-----------------------------+

+-----------------------------+
|  systemd                    |
|  collector.service          |
|    Restart=always           |
|    RestartSec=5             |
|    logs -> journalctl       |
+-----------------------------+
```

---

## Anomaly Detection: Two Layers

### Layer 1: Statistical (preprocessing.py)

Per-metric rolling window of the last 60 readings (5 minutes at 5s intervals). A reading is flagged if it exceeds `mean + 2 * std` of the window. Needs 10 readings to warm up.

Advantage: no training required, works immediately on first run.
Limitation: thresholds adapt to recent history, not learned from actual workload baseline.

### Layer 2: Isolation Forest (anomaly_model.py)

Unsupervised ML model trained on 20-30 minutes of real baseline metrics from the target machine. Learns what "normal" looks like across 8 features simultaneously:

```
cpu_percent, ram_used_gb, disk_read_mbs, disk_write_mbs,
gpu_util, gpu_mem_gb, net_in_mbs, net_out_mbs
```

Flags system states that deviate from the learned baseline. More meaningful than fixed thresholds because it is trained on YOUR machine's actual normal behaviour.

Both layers write separate anomaly fields to InfluxDB and are visible independently in Grafana.

---

## Data Schema

All measurements tagged with `host` for multi-machine support.

| Measurement | Key Fields | Extra Tags |
|---|---|---|
| cpu_usage | usage_percent, anomaly | |
| memory | total_kb, used_kb, cached_kb, buffers_kb, free_kb, anomaly | |
| disk_usage | usage_percent, total_bytes, free_bytes | |
| disk_io | read_bytes_per_sec, write_bytes_per_sec, anomaly | device |
| gpu | utilization_percent, memory_used_mb, memory_total_mb, temperature_c, power_draw_w, anomaly | |
| network | bytes_in_per_sec, bytes_out_per_sec, anomaly | interface |
| bottleneck_flags | flag, severity | |
| ml_anomaly | is_anomaly | |
| training_run | event, config | run_name |

---

## Bottleneck Rules

| Rule | Condition | Severity |
|---|---|---|
| DataLoader bottleneck | CPU > 90% AND GPU util < 60% | warning |
| GPU memory leak | GPU memory growing 5 ticks in a row | critical |
| Disk full soon | Estimated full in < 4 hours at current write rate | critical |

---

## Collector Modes

**Normal mode** (main daemon):
```bash
python3 python_collector/main_loop.py
```
Collects, detects, writes to InfluxDB every 5 seconds. Loads ML model if trained.

**Collect-only mode** (for ML training data):
```bash
python3 python_collector/main_loop.py --collect-only --output=data/training_data.csv
```
Writes CSV rows instead of InfluxDB. Run for 20-30 min to build training dataset.

**Train ML model:**
```bash
python3 python_collector/anomaly_model.py --train
```

---

## File Structure

```
ml-infra-monitor/
├── python_collector/
│   ├── main_loop.py          entry point, 5s daemon loop
│   ├── data_collection.py    reads /proc and nvidia-smi
│   ├── preprocessing.py      delta math, statistical anomaly, bottleneck rules
│   ├── sending_to_db.py      InfluxDB write client
│   ├── anomaly_model.py      Isolation Forest train + inference
│   ├── tag_run.py            training run tagger CLI
│   ├── generate_report.py    post-run markdown report generator
│   ├── config.py             loads .env
│   └── requirements.txt
├── docker/
│   └── docker-compose.yml    InfluxDB 2.7 + Grafana
├── systemd/
│   └── collector.service     auto-start, restart on crash
├── scripts/
│   ├── setup.sh              install deps, start Docker, create dirs
│   ├── service.sh            deploy + enable systemd service
│   ├── monitor.sh            bash terminal dashboard (reads /proc directly)
│   ├── log_parser.sh         extract anomaly events from journalctl
│   ├── benchmark.sh          stress test + verify detector response
│   └── report.sh             wrapper for generate_report.py
├── grafana/
│   └── dashboards/
│       └── ml_monitor.json   pre-built dashboard, import directly
├── models/                   anomaly_model.pkl + scaler.pkl (gitignored)
├── data/                     training_data.csv (gitignored)
├── reports/                  generated run reports (gitignored)
├── .env.example
├── .gitignore
└── README.md
```
