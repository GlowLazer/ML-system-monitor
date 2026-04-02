import os
from dotenv import load_dotenv

load_dotenv()

INFLUXDB_URL     = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN   = os.getenv("INFLUXDB_TOKEN", "")
INFLUXDB_ORG     = os.getenv("INFLUXDB_ORG", "iitjammu")
INFLUXDB_BUCKET  = os.getenv("INFLUXDB_BUCKET", "ml_metrics")
COLLECT_INTERVAL = int(os.getenv("COLLECT_INTERVAL", "5"))
HOST_TAG         = os.getenv("HOST_TAG", "localhost")
