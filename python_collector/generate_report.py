import argparse
from datetime import datetime
from influxdb_client import InfluxDBClient

import config


def query_mean(query_api, measurement: str, field: str, time_range: str) -> str:
    query = f'''
    from(bucket: "{config.INFLUXDB_BUCKET}")
      |> range(start: {time_range})
      |> filter(fn: (r) => r._measurement == "{measurement}")
      |> filter(fn: (r) => r._field == "{field}")
      |> filter(fn: (r) => r.host == "{config.HOST_TAG}")
      |> mean()
    '''
    try:
        result = query_api.query(query)
        if result and result[0].records:
            return f"{result[0].records[0].get_value():.2f}"
    except Exception:
        pass
    return "N/A"


def query_max(query_api, measurement: str, field: str, time_range: str) -> str:
    query = f'''
    from(bucket: "{config.INFLUXDB_BUCKET}")
      |> range(start: {time_range})
      |> filter(fn: (r) => r._measurement == "{measurement}")
      |> filter(fn: (r) => r._field == "{field}")
      |> filter(fn: (r) => r.host == "{config.HOST_TAG}")
      |> max()
    '''
    try:
        result = query_api.query(query)
        if result and result[0].records:
            return f"{result[0].records[0].get_value():.2f}"
    except Exception:
        pass
    return "N/A"


def query_anomaly_count(query_api, time_range: str) -> int:
    # counts how many ticks had either rule-based or ML anomaly flagged
    query = f'''
    from(bucket: "{config.INFLUXDB_BUCKET}")
      |> range(start: {time_range})
      |> filter(fn: (r) => r._measurement == "ml_anomaly" or r._measurement == "cpu_usage")
      |> filter(fn: (r) => r._field == "anomaly" or r._field == "is_anomaly")
      |> filter(fn: (r) => r._value == true)
      |> count()
    '''
    try:
        result = query_api.query(query)
        if result and result[0].records:
            return result[0].records[0].get_value()
    except Exception:
        pass
    return 0


def query_bottlenecks(query_api, time_range: str) -> list:
    query = f'''
    from(bucket: "{config.INFLUXDB_BUCKET}")
      |> range(start: {time_range})
      |> filter(fn: (r) => r._measurement == "bottleneck_flags")
      |> filter(fn: (r) => r._field == "flag")
      |> filter(fn: (r) => r.host == "{config.HOST_TAG}")
      |> distinct(column: "_value")
    '''
    flags = []
    try:
        result = query_api.query(query)
        if result:
            for record in result[0].records:
                flags.append(record.get_value())
    except Exception:
        pass
    return flags


# generates a markdown report for a named training run
# time_range is an InfluxDB duration string like -1h or -24h
def generate(run_name: str, output: str, time_range: str = "-24h"):
    client = InfluxDBClient(
        url=config.INFLUXDB_URL,
        token=config.INFLUXDB_TOKEN,
        org=config.INFLUXDB_ORG,
    )
    q = client.query_api()

    avg_cpu    = query_mean(q, "cpu_usage", "usage_percent",       time_range)
    avg_gpu    = query_mean(q, "gpu",       "utilization_percent", time_range)
    avg_mem    = query_mean(q, "memory",    "used_kb",             time_range)
    peak_cpu   = query_max(q,  "cpu_usage", "usage_percent",       time_range)
    peak_temp  = query_max(q,  "gpu",       "temperature_c",       time_range)
    peak_power = query_max(q,  "gpu",       "power_draw_w",        time_range)
    anomalies  = query_anomaly_count(q, time_range)
    bottlenecks = query_bottlenecks(q, time_range)

    client.close()

    bn_lines = "\n".join(f"- {b}" for b in bottlenecks) if bottlenecks else "- None"

    report = f"""# Run Report: {run_name}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Host: {config.HOST_TAG}

## Summary
| Metric | Avg | Peak |
|---|---|---|
| CPU Usage | {avg_cpu}% | {peak_cpu}% |
| GPU Utilization | {avg_gpu}% | N/A |
| RAM Used | {avg_mem} kB | N/A |
| GPU Temperature | N/A | {peak_temp} C |
| GPU Power | N/A | {peak_power} W |

## Anomalies Detected
Total anomaly events: {anomalies}

## Bottlenecks
{bn_lines}
"""

    with open(output, "w") as f:
        f.write(report)
    print(f"Report saved to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a post-run markdown report")
    parser.add_argument("--run",    required=True, help="Run name")
    parser.add_argument("--output", required=True, help="Output file path e.g. reports/run1.md")
    parser.add_argument("--range",  default="-24h", help="InfluxDB time range e.g. -1h -24h")
    args = parser.parse_args()

    generate(args.run, args.output, args.range)
