import subprocess


# reads /proc/stat which the linux kernel updates every tick
# returns raw idle ticks and total ticks (not a percentage yet, we need two snapshots to compute that)
# also grabs context switches (ctxt) and interrupts (intr) for future use
def read_cpu(command="/proc/stat") -> tuple[int, int, int, int]:
    with open(command) as f:
        lines = f.readlines()

    # first line is total cpu across all cores
    states_cpu = lines[0].split()
    if states_cpu[0] != "cpu":
        raise ValueError(f"Unexpected format in {command}")

    int_states = list(map(int, states_cpu[1:]))

    idle_time = int_states[3]
    total_time = sum(int_states)

    ctxt = 0
    intr = 0
    for line in lines:
        if line.startswith("ctxt"):
            ctxt = int(line.split()[1])
        elif line.startswith("intr"):
            intr = int(line.split()[1])

    return idle_time, total_time, ctxt, intr


# reads /proc/meminfo which linux keeps updated in real time
# MemAvailable is better than MemFree because it accounts for reclaimable cache
# total_used = total - available (not total - free, that would ignore cache)
def read_memory(command="/proc/meminfo") -> tuple[int, int, int, int, int]:
    memory_info = {}
    with open(command) as f:
        for line in f:
            key, value = line.split(":")
            memory_info[key] = value.strip()

    total_memory = int(memory_info["MemTotal"].split()[0])
    free = int(memory_info["MemFree"].split()[0])
    available = int(memory_info["MemAvailable"].split()[0])
    cached = int(memory_info["Cached"].split()[0])
    buffers = int(memory_info["Buffers"].split()[0])

    total_used = total_memory - available

    return total_memory, total_used, cached, buffers, free


# calls nvidia-smi to get gpu stats, it is the standard nvidia tool for this
# power.draw can return a float like 150.5 so we parse it as float not int
# if nvidia-smi is not found or fails (no gpu, driver issue) we return zeros so the rest of the loop keeps running
def read_gpu() -> tuple[float, float, int, int, int, float]:
    try:
        result = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ]
        ).decode("utf-8").strip()

        parts = result.split(",")
        gpu_util  = float(parts[0].strip())
        mem_util  = float(parts[1].strip())
        mem_used  = int(parts[2].strip())
        mem_total = int(parts[3].strip())
        gpu_temp  = int(parts[4].strip())
        power     = float(parts[5].strip())

        return gpu_util, mem_util, mem_used, mem_total, gpu_temp, power

    except Exception as e:
        print("GPU read error:", e)
        return 0.0, 0.0, 0, 0, 0, 0.0


# uses df -B1 to get exact byte counts instead of human readable sizes like "50G"
# we need raw numbers so we can do math on them (e.g. disk full prediction)
def read_disk_usage() -> tuple[float, int, int]:
    try:
        result = subprocess.check_output(["df", "-B1", "/"]).decode("utf-8")
        data = result.strip().split("\n")[1].split()

        total_bytes = int(data[1])
        free_bytes  = int(data[3])
        percent     = float(data[4].replace("%", ""))

        return percent, total_bytes, free_bytes

    except Exception as e:
        print("Disk usage error:", e)
        return 0.0, 0, 0


# reads /proc/diskstats which the kernel updates on every disk read/write
# returns raw cumulative sector counts, NOT per second rates
# we store this snapshot and subtract from the next one to get the rate (done in preprocessing)
# skips partitions like sda1, sda2 and only keeps physical disks like sda or nvme0n1
def read_disk_io(command="/proc/diskstats") -> dict[str, tuple[int, int]]:
    stats = {}
    try:
        with open(command) as f:
            for line in f:
                parts = line.split()
                device = parts[2]
                # only physical disks (sda, nvme0n1, etc.), skip partitions
                if not any(c.isdigit() for c in device) or "nvme" in device:
                    sectors_read    = int(parts[5])
                    sectors_written = int(parts[9])
                    stats[device] = (sectors_read, sectors_written)
    except Exception as e:
        print("Disk IO error:", e)
    return stats


# reads /proc/net/dev which the kernel keeps as running byte counters per interface
# same deal as disk io, returns raw cumulative counts, rate is computed in preprocessing
# skips loopback (lo) since that is just internal traffic and not useful to monitor
def read_network(command="/proc/net/dev") -> dict[str, tuple[int, int]]:
    stats = {}
    try:
        with open(command) as f:
            lines = f.readlines()[2:]  # skip header rows

        for line in lines:
            parts = line.split()
            iface = parts[0].rstrip(":")
            if iface == "lo":
                continue
            bytes_recv = int(parts[1])
            bytes_sent = int(parts[9])
            stats[iface] = (bytes_recv, bytes_sent)

    except Exception as e:
        print("Network read error:", e)
    return stats
