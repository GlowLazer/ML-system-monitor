#!/bin/bash
set -e

echo "=== ML Infra Monitor Setup ==="

echo "[1/4] Installing Python dependencies..."
pip install -r python_collector/requirements.txt

echo "[2/4] Setting up .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env  -- add your InfluxDB token before running."
else
    echo ".env already exists, skipping."
fi

echo "[3/4] Starting Docker stack..."
cd docker && docker-compose up -d && cd ..

echo "[4/4] Creating data directories..."
mkdir -p models reports data

echo ""
echo "Done. Next steps:"
echo "  1. Open InfluxDB at http://localhost:8086, create a token, paste it into .env"
echo "  2. Run:  python3 python_collector/main_loop.py"
echo "  3. Open Grafana at http://localhost:3000"
