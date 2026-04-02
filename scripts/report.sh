#!/bin/bash
# report.sh - wrapper to generate a markdown report for a named training run
# usage: ./scripts/report.sh <run-name> [time-range]
# example: ./scripts/report.sh resnet50-run1 -1h

set -e

RUN_NAME=$1
TIME_RANGE=${2:--24h}

if [ -z "$RUN_NAME" ]; then
    echo "Usage: $0 <run-name> [time-range]"
    echo "  time-range defaults to -24h"
    echo "  example: $0 resnet50-run1 -1h"
    exit 1
fi

mkdir -p reports

python3 python_collector/generate_report.py \
    --run    "$RUN_NAME" \
    --output "reports/${RUN_NAME}.md" \
    --range  "$TIME_RANGE"

echo "Report: reports/${RUN_NAME}.md"
