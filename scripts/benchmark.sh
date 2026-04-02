#!/bin/bash
# benchmark.sh - stress the system and verify the anomaly detector responds
# runs CPU and disk stress, then checks journalctl for anomaly events
# needs: stress (installed automatically), collector service running

set -e

echo "=== ML Infra Monitor - Benchmark & Validation ==="
echo ""

# make sure the collector is running so there is something to detect the stress
if ! systemctl is-active --quiet collector; then
    echo "Warning: collector service is not running. Start it first."
    echo "  sudo systemctl start collector"
    echo "  OR run: python3 python_collector/main_loop.py"
    exit 1
fi

# install stress if missing
if ! command -v stress &>/dev/null; then
    echo "Installing stress..."
    sudo apt-get install -y stress
fi

echo "[1/3] Stressing CPU for 30 seconds (all cores)..."
stress --cpu "$(nproc)" --timeout 30
echo "CPU stress done."
echo ""

echo "[2/3] Stressing disk I/O (writing 512MB to /tmp)..."
dd if=/dev/zero of=/tmp/ml_monitor_bench bs=1M count=512 oflag=direct 2>&1
rm -f /tmp/ml_monitor_bench
echo "Disk stress done."
echo ""

# wait a couple intervals so the collector has time to write the spike to InfluxDB
echo "[3/3] Waiting 10s for collector to catch up..."
sleep 10

echo "Checking collector log for anomaly responses..."
echo ""
bash "$(dirname "$0")/log_parser.sh" 100

echo ""
echo "=== Benchmark complete ==="
echo "Check Grafana dashboard for the spike visualization."
