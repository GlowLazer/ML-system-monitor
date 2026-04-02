import argparse
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

import config


# writes a start or end event to the training_run measurement in InfluxDB
# grafana can read these and draw vertical annotation lines on the dashboard
# so you can see exactly when a training run happened relative to your metrics
def tag(name: str, run_config: str = "", end: bool = False):
    client = InfluxDBClient(
        url=config.INFLUXDB_URL,
        token=config.INFLUXDB_TOKEN,
        org=config.INFLUXDB_ORG,
    )
    write_api = client.write_api(write_options=SYNCHRONOUS)

    event = "end" if end else "start"
    point = (
        Point("training_run")
        .tag("host",     config.HOST_TAG)
        .tag("run_name", name)
        .field("event",  event)
        .field("config", run_config)
        .time(datetime.now(timezone.utc))
    )
    write_api.write(bucket=config.INFLUXDB_BUCKET, org=config.INFLUXDB_ORG, record=point)
    client.close()
    print(f"Tagged run '{name}' as {event}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tag a training run in InfluxDB")
    parser.add_argument("--name",   required=True,       help="Run name e.g. resnet50-run1")
    parser.add_argument("--config", default="",          help="Training config string e.g. lr=0.001,batch=32")
    parser.add_argument("--end",    action="store_true", help="Mark this run as finished")
    args = parser.parse_args()

    tag(args.name, args.config, args.end)
