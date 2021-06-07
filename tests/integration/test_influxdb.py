import csv
import time
from datetime import datetime
from typing import Any, Dict, List

import pytest
import requests
from yarl import URL

from .conftest import MainProcessFixture, OPCServer

INFLUXDB_HOST = "influxdb"
INFLUXDB_ORG = "testorg"
INFLUXDB_BUCKET = "testbucket"
INFLUXDB_TOKEN = (
    "zsQmRXoNWcQU4jsJxGOMQqwu5KLNGUhsxg4KZ2YRypNP"  # noqa: S105
    "C8FV7VUlygO4YndqHFlY4KwoOe5Dt0nrosEvDJYkiQ=="
)


class InfluxDB:
    def __init__(self) -> None:
        self.root_url = URL(f"http://{INFLUXDB_HOST}:8086")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Token {INFLUXDB_TOKEN}"})
        self.session.params = {"org": INFLUXDB_ORG}

    def url(self, endpoint: str) -> str:
        return str(self.root_url / endpoint)

    def clear(self) -> None:
        data = {
            "start": "1970-01-01T00:00:00Z",
            "stop": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        resp = self.session.post(
            self.url("api/v2/delete"), params={"bucket": INFLUXDB_BUCKET}, json=data
        )
        resp.raise_for_status()

    def query(self, query: str) -> List[Dict[str, Any]]:
        resp = self.session.post(
            self.url("api/v2/query"),
            headers={"Content-Type": "application/vnd.flux"},
            data=query,
        )
        resp.raise_for_status()
        return list(csv.DictReader(resp.text.splitlines()))

    def ping(self) -> bool:
        try:
            resp = requests.get(self.url("ready"))
            resp.raise_for_status()
        except requests.RequestException:
            return False
        resp = requests.get(self.url("api/v2/setup"))
        return resp.json()["allowed"] is False


@pytest.fixture()
def influxdb() -> InfluxDB:
    _influxdb = InfluxDB()
    start_time = datetime.now()
    while not _influxdb.ping():
        elapsed = datetime.now() - start_time
        assert elapsed.total_seconds() < 30, "Timeout waiting for InfluxDB to be ready"
        time.sleep(1.0)
    _influxdb.clear()
    return _influxdb


def test_smoketest(
    influxdb: InfluxDB,
    main_process: MainProcessFixture,
    mandatory_env_args: Dict[str, str],
    opcserver: OPCServer,
) -> None:
    envargs = dict(
        mandatory_env_args,
        INFLUXDB_ORG=INFLUXDB_ORG,
        INFLUXDB_BUCKET=INFLUXDB_BUCKET,
        INFLUXDB_WRITE_TOKEN=INFLUXDB_TOKEN,
        INFLUXDB_BASE_URL=str(influxdb.root_url),
    )
    process = main_process([], envargs)
    start_time = datetime.now()
    while not opcserver.has_subscriptions():
        elapsed = datetime.now() - start_time
        assert (
            elapsed.total_seconds() < 10
        ), "Timeout waiting for OPC-UA server to have subscriptions"
        time.sleep(1.0)
        assert process.poll() is None
    # InfluxDB time precision is set to second at write, so sleep to be sure
    # to not overwrite the last point
    time.sleep(1.0)
    opcserver.change_node("recorded")
    lines: List[Dict[str, Any]] = []
    start_time = datetime.now()
    while not lines:
        elapsed = datetime.now() - start_time
        assert elapsed.total_seconds() < 10, "Timeout waiting InfluxDB to have series"
        lines = influxdb.query(
            f"""import "influxdata/influxdb/schema"
            schema.measurements(bucket: "{INFLUXDB_BUCKET}")"""
        )
        time.sleep(1.0)
    assert all(line["_value"] == "Recorded" for line in lines)
    lines = influxdb.query(
        f"""from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -1h)
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
        """
    )
    expected_items = [
        (("Recorded_index", "0"), ("Active", "true"), ("Age", "18")),
        (("Recorded_index", "0"), ("Active", "false"), ("Age", "67")),
        (("Recorded_index", "1"), ("Active", "false"), ("Age", "32")),
        (("Recorded_index", "1"), ("Active", "true"), ("Age", "12")),
    ]
    for items in expected_items:
        assert lines.pop(0).items() > set(items), f"Got lines:\n{lines}"
    assert len(lines) == 0  # All lines must have been consumed
