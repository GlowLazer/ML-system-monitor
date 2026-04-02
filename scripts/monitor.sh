#!/bin/bash
# monitor.sh - lightweight terminal ML monitor
# reads /proc directly, no Python, no psutil
# this is the point of the bash script - show linux internals knowledge

tput civis  # hide cursor

cleanup() {
    tput cnorm
    tput clear
    exit 0
}
trap cleanup SIGINT SIGTERM

# we need two cpu snapshots to compute usage, grab the first one here
read_cpu_snapshot() {
    awk '/^cpu / {print $2+$3+$4+$5+$6+$7+$8, $5}' /proc/stat
}

prev_snapshot=$(read_cpu_snapshot)
prev_total=$(echo "$prev_snapshot" | awk '{print $1}')
prev_idle=$(echo  "$prev_snapshot" | awk '{print $2}')

sleep 1

while true; do
    tput cup 0 0

    # CPU - same delta approach as the Python collector
    curr_snapshot=$(read_cpu_snapshot)
    curr_total=$(echo "$curr_snapshot" | awk '{print $1}')
    curr_idle=$(echo  "$curr_snapshot" | awk '{print $2}')

    delta_total=$(( curr_total - prev_total ))
    delta_idle=$(( curr_idle - prev_idle ))

    if [ "$delta_total" -gt 0 ]; then
        cpu_used=$(( (delta_total - delta_idle) * 100 / delta_total ))
    else
        cpu_used=0
    fi

    prev_total=$curr_total
    prev_idle=$curr_idle

    # RAM - from /proc/meminfo, values are in kB
    mem_total=$(awk '/MemTotal/    {print $2}' /proc/meminfo)
    mem_avail=$(awk '/MemAvailable/{print $2}' /proc/meminfo)
    mem_used_kb=$(( mem_total - mem_avail ))
    mem_used_mb=$(( mem_used_kb / 1024 ))
    mem_total_mb=$(( mem_total / 1024 ))

    # Disk usage on /
    disk_used=$(df / --output=pcent 2>/dev/null | tail -1 | tr -d ' %')

    # GPU via nvidia-smi if available
    if command -v nvidia-smi &>/dev/null; then
        gpu_line=$(nvidia-smi \
            --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw \
            --format=csv,noheader,nounits 2>/dev/null)
        gpu_util=$(echo "$gpu_line" | awk -F',' '{gsub(/ /,"",$1); print $1}')
        gpu_mem_used=$(echo "$gpu_line" | awk -F',' '{gsub(/ /,"",$2); print $2}')
        gpu_mem_total=$(echo "$gpu_line" | awk -F',' '{gsub(/ /,"",$3); print $3}')
        gpu_temp=$(echo "$gpu_line" | awk -F',' '{gsub(/ /,"",$4); print $4}')
        gpu_power=$(echo "$gpu_line" | awk -F',' '{gsub(/ /,"",$5); print $5}')
    else
        gpu_util="N/A"
        gpu_mem_used="N/A"
        gpu_mem_total="N/A"
        gpu_temp="N/A"
        gpu_power="N/A"
    fi

    echo "========================================"
    echo "      ML Infrastructure Monitor         "
    echo "========================================"
    printf "  CPU Usage    : %s%%\n"         "$cpu_used"
    printf "  RAM Used     : %s / %s MB\n"   "$mem_used_mb" "$mem_total_mb"
    printf "  Disk Used    : %s%%\n"         "$disk_used"
    echo "  ---- GPU ----"
    printf "  GPU Util     : %s%%\n"         "$gpu_util"
    printf "  GPU Memory   : %s / %s MiB\n"  "$gpu_mem_used" "$gpu_mem_total"
    printf "  GPU Temp     : %s C\n"         "$gpu_temp"
    printf "  GPU Power    : %s W\n"         "$gpu_power"
    echo "========================================"
    printf "  %s   [Ctrl+C to exit]\n"       "$(date '+%H:%M:%S')"

    sleep 2
done
