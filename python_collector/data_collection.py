import shutil 
import subprocess

def read_cpu(command="/proc/stat") -> tuple[int, int, int, int]:
    with open(command) as f:
        lines = f.readlines()

    # first line → total cpu
    states_cpu = lines[0].split()
    if states_cpu[0] != "cpu":
        raise ValueError(f"This format is not expected in this {command}")

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

def read_gpu() -> tuple[int, int, int, int, int, int]:
    try:
        result = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits"
            ]
        ).decode("utf-8").strip()

        values = [int(x.strip()) for x in result.split(",")]

        gpu_util = values[0]
        mem_util = values[1]
        mem_used = values[2]
        mem_total = values[3]
        gpu_temp = values[4]
        power = values[5]

        return gpu_util, mem_util, mem_used, mem_total, gpu_temp, power

    except Exception as e:
        print("GPU read error:", e)
        return 0, 0, 0, 0, 0, 0
    
def read_disk(command=["df", "-h", "/"]) -> tuple[str, str, str, str, float]:
    try:
        result = subprocess.check_output(command).decode("utf-8")

        lines = result.strip().split("\n")
        data = lines[1].split()

        size = data[1]
        used = data[2]
        available = data[3]
        used_percentage = data[4]
        percent = float(used_percentage.replace("%", ""))
        return size, used, available, used_percentage, percent

    except Exception as e:
        print("Disk error:", e)
        return None

# now after getting the data we have to build the functions that will turn these functions into the 
# meaningful metrics so that we can draw the graph between the usage and the time 
# data -> processing -> sending to database -> then main_loop so that it can run automatically after the require time 
