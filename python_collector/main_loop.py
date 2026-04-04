import time

import config
import data_collection as dc
import preprocessing   as pp
import sending_to_db   as db


def run():
    print(f"Starting collector  interval: {config.COLLECT_INTERVAL}s  host: {config.HOST_TAG}")

    # anomaly detector is created once here so it keeps its rolling windows across every tick
    # if we created it inside the loop it would reset every 5 seconds and never accumulate history
    detector = pp.AnomalyDetector(window_size=60)
    gpu_mem_history = []

    # initial snapshots for delta-based metrics (cpu, disk io, network)
    prev_cpu     = dc.read_cpu()
    prev_disk_io = dc.read_disk_io()
    prev_net     = dc.read_network()
    prev_time    = time.time()

    time.sleep(config.COLLECT_INTERVAL)

    while True:
        tick_start = time.time()
        interval   = tick_start - prev_time  # actual elapsed time, not assumed to be exactly 5s

        try:
            # collect
            curr_cpu     = dc.read_cpu()
            mem          = dc.read_memory()
            disk_usage   = dc.read_disk_usage()
            curr_disk_io = dc.read_disk_io()
            gpu          = dc.read_gpu()
            curr_net     = dc.read_network()

            # preprocess: turn raw snapshots into rates and percentages
            cpu_percent = pp.compute_cpu_percent(prev_cpu, curr_cpu)
            disk_io     = pp.compute_disk_io(prev_disk_io, curr_disk_io, interval)
            net_io      = pp.compute_network_io(prev_net, curr_net, interval)

            total_mem_kb, used_mem_kb, cached_kb, buffers_kb, free_kb = mem
            disk_percent, total_bytes, free_bytes = disk_usage
            gpu_util, mem_util, mem_used, mem_total, gpu_temp, power  = gpu

            gpu_mem_history.append(mem_used)
            if len(gpu_mem_history) > 60:
                gpu_mem_history.pop(0)

            # statistical anomaly detection: rolling mean +/- 2 sigma per metric
            cpu_anomaly = detector.check("cpu",      cpu_percent)
            mem_anomaly = detector.check("memory",   used_mem_kb)
            gpu_anomaly = detector.check("gpu_util", gpu_util)

            # send to influxdb
            db.send_cpu(cpu_percent, cpu_anomaly)
            db.send_memory(total_mem_kb, used_mem_kb, cached_kb, buffers_kb, free_kb, mem_anomaly)
            db.send_disk_usage(disk_percent, total_bytes, free_bytes)
            db.send_gpu(gpu_util, mem_util, mem_used, mem_total, gpu_temp, power, gpu_anomaly)

            for device, stats in disk_io.items():
                d_anomaly = detector.check(f"disk_io_{device}", stats["write_bytes_per_sec"])
                db.send_disk_io(device, stats["read_bytes_per_sec"], stats["write_bytes_per_sec"], d_anomaly)

            for iface, stats in net_io.items():
                n_anomaly = detector.check(f"net_{iface}", stats["bytes_in_per_sec"])
                db.send_network(iface, stats["bytes_in_per_sec"], stats["bytes_out_per_sec"], n_anomaly)

            # bottleneck rules
            flags = pp.detect_bottlenecks(cpu_percent, gpu_util, gpu_mem_history)

            if disk_io:
                first_device = next(iter(disk_io))
                write_bps = disk_io[first_device]["write_bytes_per_sec"]
                disk_flag = pp.predict_disk_full(disk_percent, write_bps, total_bytes)
                if disk_flag:
                    flags.append(disk_flag)

            for flag, severity in flags:
                db.send_bottleneck(flag, severity)
                print(f"[BOTTLENECK] {severity.upper()}: {flag}")

            # update snapshots for next tick
            prev_cpu     = curr_cpu
            prev_disk_io = curr_disk_io
            prev_net     = curr_net
            prev_time    = tick_start

        except Exception as e:
            print("Collector error:", e)

        # sleep for the remainder of the interval
        elapsed = time.time() - tick_start
        time.sleep(max(0, config.COLLECT_INTERVAL - elapsed))


if __name__ == "__main__":
    run()
