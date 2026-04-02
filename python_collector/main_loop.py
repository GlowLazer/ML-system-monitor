import sys
import time
import csv
import os

import config
import data_collection as dc
import preprocessing   as pp
import sending_to_db   as db


def _load_model():
    # try to load the trained Isolation Forest model
    # if it doesn't exist yet (before training), we skip ML inference and warn once
    try:
        import anomaly_model as am
        model, scaler = am.load()
        print("ML anomaly model loaded.")
        return am, model, scaler
    except FileNotFoundError:
        print("Warning: ML model not found. Run 'python3 anomaly_model.py --train' after collecting data.")
        print("Continuing with rule-based anomaly detection only.")
        return None, None, None


def _build_ml_features(cpu_percent, used_mem_kb, disk_io, gpu_util, mem_used, net_io):
    # converts current tick values into the feature dict the ML model expects
    # aggregates across all devices/interfaces by summing
    disk_read_mbs  = sum(s["read_bytes_per_sec"]  for s in disk_io.values()) / (1024 * 1024)
    disk_write_mbs = sum(s["write_bytes_per_sec"] for s in disk_io.values()) / (1024 * 1024)
    net_in_mbs     = sum(s["bytes_in_per_sec"]    for s in net_io.values())  / (1024 * 1024)
    net_out_mbs    = sum(s["bytes_out_per_sec"]   for s in net_io.values())  / (1024 * 1024)

    return {
        "cpu_percent":    cpu_percent,
        "ram_used_gb":    used_mem_kb / (1024 * 1024),
        "disk_read_mbs":  disk_read_mbs,
        "disk_write_mbs": disk_write_mbs,
        "gpu_util":       gpu_util,
        "gpu_mem_gb":     mem_used / 1024,
        "net_in_mbs":     net_in_mbs,
        "net_out_mbs":    net_out_mbs,
    }


def _init_csv(output_path: str):
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    f = open(output_path, "w", newline="")
    writer = csv.DictWriter(f, fieldnames=[
        "timestamp", "cpu_percent", "ram_used_gb",
        "disk_read_mbs", "disk_write_mbs",
        "gpu_util", "gpu_mem_gb",
        "net_in_mbs", "net_out_mbs",
    ])
    writer.writeheader()
    return f, writer


def run(collect_only: bool = False, csv_output: str = "data/training_data.csv"):
    mode = "collect-only (CSV)" if collect_only else "normal"
    print(f"Starting collector  mode: {mode}  interval: {config.COLLECT_INTERVAL}s  host: {config.HOST_TAG}")

    # load ML model once at startup, not inside the loop
    am, model, scaler = _load_model() if not collect_only else (None, None, None)

    detector = pp.AnomalyDetector(window_size=60)
    gpu_mem_history = []

    csv_file, csv_writer = None, None
    if collect_only:
        csv_file, csv_writer = _init_csv(csv_output)
        print(f"Writing training data to {csv_output}")

    # initial snapshots for delta-based metrics
    prev_cpu     = dc.read_cpu()
    prev_disk_io = dc.read_disk_io()
    prev_net     = dc.read_network()
    prev_time    = time.time()

    time.sleep(config.COLLECT_INTERVAL)

    try:
        while True:
            tick_start = time.time()
            interval   = tick_start - prev_time

            try:
                # collect
                curr_cpu     = dc.read_cpu()
                mem          = dc.read_memory()
                disk_usage   = dc.read_disk_usage()
                curr_disk_io = dc.read_disk_io()
                gpu          = dc.read_gpu()
                curr_net     = dc.read_network()

                # preprocess
                cpu_percent = pp.compute_cpu_percent(prev_cpu, curr_cpu)
                disk_io     = pp.compute_disk_io(prev_disk_io, curr_disk_io, interval)
                net_io      = pp.compute_network_io(prev_net, curr_net, interval)

                total_mem_kb, used_mem_kb, cached_kb, buffers_kb, free_kb = mem
                disk_percent, total_bytes, free_bytes = disk_usage
                gpu_util, mem_util, mem_used, mem_total, gpu_temp, power  = gpu

                gpu_mem_history.append(mem_used)
                if len(gpu_mem_history) > 60:
                    gpu_mem_history.pop(0)

                features = _build_ml_features(
                    cpu_percent, used_mem_kb, disk_io, gpu_util, mem_used, net_io
                )

                if collect_only:
                    # in collect-only mode just save the row to CSV, no DB writes
                    row = {"timestamp": tick_start}
                    row.update(features)
                    csv_writer.writerow(row)
                    csv_file.flush()
                    print(f"  cpu={cpu_percent:.1f}%  gpu={gpu_util:.1f}%  ram={features['ram_used_gb']:.2f}GB")
                else:
                    # rule-based anomaly flags
                    cpu_anomaly = detector.check("cpu",      cpu_percent)
                    mem_anomaly = detector.check("memory",   used_mem_kb)
                    gpu_anomaly = detector.check("gpu_util", gpu_util)

                    # ML model inference (skipped if model not trained yet)
                    if model is not None:
                        ml_anomaly = am.predict(model, scaler, features)
                        db.send_ml_anomaly(ml_anomaly)
                        if ml_anomaly:
                            print("[ML ANOMALY] system behaviour outside learned baseline")

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

                # update snapshots
                prev_cpu     = curr_cpu
                prev_disk_io = curr_disk_io
                prev_net     = curr_net
                prev_time    = tick_start

            except Exception as e:
                print("Collector error:", e)

            elapsed = time.time() - tick_start
            time.sleep(max(0, config.COLLECT_INTERVAL - elapsed))

    finally:
        if csv_file:
            csv_file.close()


if __name__ == "__main__":
    collect_only = "--collect-only" in sys.argv
    output = "data/training_data.csv"
    for arg in sys.argv:
        if arg.startswith("--output="):
            output = arg.split("=", 1)[1]
    run(collect_only=collect_only, csv_output=output)
