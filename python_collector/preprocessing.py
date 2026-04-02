import numpy as np


# --- CPU ---

# /proc/stat gives cumulative ticks since boot, not a live percentage
# to get actual cpu usage we take two snapshots and compute what changed
# formula: 1 - (idle ticks gained / total ticks gained) = fraction of time cpu was busy
def compute_cpu_percent(prev: tuple, curr: tuple) -> float:
    prev_idle,  prev_total  = prev[0], prev[1]
    curr_idle,  curr_total  = curr[0], curr[1]

    delta_idle  = curr_idle  - prev_idle
    delta_total = curr_total - prev_total

    if delta_total == 0:
        return 0.0

    return round((1 - delta_idle / delta_total) * 100, 2)


# --- Disk I/O ---

SECTOR_SIZE = 512  # linux always reports disk sectors as 512 bytes regardless of physical sector size

# same idea as cpu, /proc/diskstats gives cumulative sector counts since boot
# subtract prev snapshot from current, divide by time elapsed to get per-second rate
def compute_disk_io(prev: dict, curr: dict, interval: float) -> dict:
    result = {}
    for device in curr:
        if device not in prev:
            continue
        read_sectors  = curr[device][0] - prev[device][0]
        write_sectors = curr[device][1] - prev[device][1]
        result[device] = {
            "read_bytes_per_sec":  round((read_sectors  * SECTOR_SIZE) / interval, 2),
            "write_bytes_per_sec": round((write_sectors * SECTOR_SIZE) / interval, 2),
        }
    return result


# --- Network ---

# /proc/net/dev also gives cumulative byte counts since boot
# same delta approach: current minus previous divided by elapsed time
def compute_network_io(prev: dict, curr: dict, interval: float) -> dict:
    result = {}
    for iface in curr:
        if iface not in prev:
            continue
        bytes_in  = curr[iface][0] - prev[iface][0]
        bytes_out = curr[iface][1] - prev[iface][1]
        result[iface] = {
            "bytes_in_per_sec":  round(bytes_in  / interval, 2),
            "bytes_out_per_sec": round(bytes_out / interval, 2),
        }
    return result


# --- Anomaly detection ---

# keeps a rolling window of the last N readings for each metric
# if the current value is more than 2 standard deviations above the average of that window, it is an anomaly
# why 2 sigma: catches genuine spikes without triggering on normal fluctuation
# why window_size=60: at 5s intervals that is the last 5 minutes of data
# needs at least 10 readings before it starts flagging, otherwise std is meaningless on tiny samples
class AnomalyDetector:
    def __init__(self, window_size=60):
        self.window_size = window_size
        self.windows = {}  # one list per metric name

    def check(self, metric_name: str, value: float) -> bool:
        if metric_name not in self.windows:
            self.windows[metric_name] = []

        window = self.windows[metric_name]
        window.append(value)

        if len(window) > self.window_size:
            window.pop(0)

        if len(window) < 10:
            return False

        mean = np.mean(window)
        std  = np.std(window)
        return float(value) > mean + 2 * std


# --- Bottleneck rules ---

# these are heuristic rules that fire based on the relationship between metrics
# a single high cpu reading means nothing, but cpu high AND gpu low means the gpu is starved for data
# the gpu memory leak check looks for 5 consecutive increases in gpu memory usage
def detect_bottlenecks(cpu_percent: float, gpu_util: float, gpu_mem_history: list) -> list:
    flags = []

    if cpu_percent > 90 and gpu_util < 60:
        flags.append(("DataLoader bottleneck", "warning"))

    if len(gpu_mem_history) > 10:
        # check if gpu memory has been growing for last 5 readings
        if all(gpu_mem_history[i] < gpu_mem_history[i + 1] for i in range(-6, -1)):
            flags.append(("GPU memory leak suspected", "critical"))

    return flags


# estimates how many hours until the disk is full based on current write rate
# only fires if we are less than 4 hours away, otherwise it is not urgent enough to flag
def predict_disk_full(usage_percent: float, write_bytes_per_sec: float, total_bytes: int) -> tuple | None:
    free_bytes = total_bytes * (1 - usage_percent / 100)
    if write_bytes_per_sec > 0:
        hours_remaining = free_bytes / (write_bytes_per_sec * 3600)
        if hours_remaining < 4:
            return ("Disk full in ~{:.1f} hrs".format(hours_remaining), "critical")
    return None
