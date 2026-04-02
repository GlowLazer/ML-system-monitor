#!/bin/bash
set -e

INSTALL_DIR="/opt/ml-infra-monitor"

echo "Installing collector to $INSTALL_DIR..."
sudo mkdir -p "$INSTALL_DIR"
sudo cp -r python_collector "$INSTALL_DIR/"
sudo cp .env "$INSTALL_DIR/.env"

echo "Installing systemd service..."
sudo cp systemd/collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable collector
sudo systemctl start collector

echo "Done. Check logs with: journalctl -u collector -f"
