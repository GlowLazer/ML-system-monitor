#!/bin/bash
# log_parser.sh - pull anomaly and bottleneck events from the collector's systemd journal
# usage: ./scripts/log_parser.sh [number of log lines to scan, default 500]

SERVICE="collector"
LINES=${1:-500}

echo "=== Anomaly Events from $SERVICE (last $LINES lines) ==="
echo ""

journalctl -u "$SERVICE" -n "$LINES" --no-pager \
    | grep -i "anomaly\|bottleneck\|critical\|warning" \
    | awk '{
        timestamp = $1 " " $2 " " $3
        $1=$2=$3=$4=$5=""
        msg = $0
        gsub(/^ +/, "", msg)
        printf "[%s] %s\n", timestamp, msg
    }'

echo ""
echo "=== Summary ==="

# grep -ic returns 1 if no matches, which would cause set -e to exit, so we use || true
total=$(journalctl -u "$SERVICE" -n "$LINES" --no-pager \
    | grep -ic "anomaly" || true)
bottlenecks=$(journalctl -u "$SERVICE" -n "$LINES" --no-pager \
    | grep -ic "bottleneck" || true)

echo "Total anomaly events : $total"
echo "Bottleneck flags     : $bottlenecks"
