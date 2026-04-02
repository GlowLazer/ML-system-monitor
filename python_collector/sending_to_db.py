from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

import config


# the client and write api are module level globals so we only create the connection once
# get_write_api() creates it on first call and reuses it after that (lazy init)
_client = None
_write_api = None


def get_client():
    global _client, _write_api
    if _client is None:
        _client = InfluxDBClient(
            url=config.INFLUXDB_URL,
            token=config.INFLUXDB_TOKEN,
            org=config.INFLUXDB_ORG,
        )
    return _client


def get_write_api():
    global _write_api
    if _write_api is None:
        _write_api = get_client().write_api(write_options=SYNCHRONOUS)
    return _write_api


# all send functions go through this, it just keeps the write call in one place
def _write(point: Point):
    get_write_api().write(bucket=config.INFLUXDB_BUCKET, org=config.INFLUXDB_ORG, record=point)


# in influxdb a Point is one row of data
# measurement = the table name (like cpu_usage, memory, gpu etc)
# tag = something you filter/group by in queries (host, device, interface)
# field = the actual numeric or string value you are storing and graphing


def send_cpu(usage_percent: float, anomaly: bool):
    p = (
        Point("cpu_usage")
        .tag("host", config.HOST_TAG)
        .field("usage_percent", usage_percent)
        .field("anomaly", anomaly)
    )
    _write(p)


def send_memory(total_kb: int, used_kb: int, cached_kb: int, buffers_kb: int, free_kb: int, anomaly: bool):
    p = (
        Point("memory")
        .tag("host", config.HOST_TAG)
        .field("total_kb",   total_kb)
        .field("used_kb",    used_kb)
        .field("cached_kb",  cached_kb)
        .field("buffers_kb", buffers_kb)
        .field("free_kb",    free_kb)
        .field("anomaly",    anomaly)
    )
    _write(p)


def send_disk_usage(usage_percent: float, total_bytes: int, free_bytes: int):
    p = (
        Point("disk_usage")
        .tag("host",  config.HOST_TAG)
        .field("usage_percent", usage_percent)
        .field("total_bytes",   total_bytes)
        .field("free_bytes",    free_bytes)
    )
    _write(p)


# device is tagged (not a field) so you can filter by disk in grafana queries
def send_disk_io(device: str, read_bps: float, write_bps: float, anomaly: bool):
    p = (
        Point("disk_io")
        .tag("host",   config.HOST_TAG)
        .tag("device", device)
        .field("read_bytes_per_sec",  read_bps)
        .field("write_bytes_per_sec", write_bps)
        .field("anomaly", anomaly)
    )
    _write(p)


def send_gpu(util: float, mem_util: float, mem_used: int, mem_total: int, temp: int, power: float, anomaly: bool):
    p = (
        Point("gpu")
        .tag("host", config.HOST_TAG)
        .field("utilization_percent", util)
        .field("mem_utilization_percent", mem_util)
        .field("memory_used_mb",  mem_used)
        .field("memory_total_mb", mem_total)
        .field("temperature_c",   temp)
        .field("power_draw_w",    power)
        .field("anomaly", anomaly)
    )
    _write(p)


# interface is tagged so you can compare eth0 vs wlan0 in grafana
def send_network(iface: str, bytes_in_per_sec: float, bytes_out_per_sec: float, anomaly: bool):
    p = (
        Point("network")
        .tag("host",      config.HOST_TAG)
        .tag("interface", iface)
        .field("bytes_in_per_sec",  bytes_in_per_sec)
        .field("bytes_out_per_sec", bytes_out_per_sec)
        .field("anomaly", anomaly)
    )
    _write(p)


# ML model anomaly is written as its own measurement so it can be shown separately in grafana
# alongside the rule-based anomaly fields that live inside cpu_usage, memory, etc.
def send_ml_anomaly(is_anomaly: bool):
    p = (
        Point("ml_anomaly")
        .tag("host", config.HOST_TAG)
        .field("is_anomaly", is_anomaly)
    )
    _write(p)


def send_bottleneck(flag: str, severity: str):
    p = (
        Point("bottleneck_flags")
        .tag("host", config.HOST_TAG)
        .field("flag",     flag)
        .field("severity", severity)
    )
    _write(p)
