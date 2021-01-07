from __future__ import annotations

import sys
import time
from pathlib import Path
from subprocess import STDOUT, Popen
from typing import TYPE_CHECKING, Callable, Dict, Generator, List

import pytest
import requests
import toml
from _pytest.fixtures import FixtureRequest
from yarl import URL

if TYPE_CHECKING:
    MainProcessFixture = Callable[[List[str]], Popen[str]]


OPC_SERVER_HTTP_PORT = 8000


@pytest.fixture(scope="session")
def console_script(request: FixtureRequest) -> str:
    pyproject = toml.load(request.config.rootpath / "pyproject.toml")
    scripts: Dict[str, str] = pyproject["tool"]["poetry"]["scripts"]
    for script, function in scripts.items():
        if "main:app" in function:
            return script
    raise ValueError("Console script not found in pyproject.toml")


@pytest.fixture
def main_process(console_script: str) -> MainProcessFixture:
    def _inner(args: List[str]) -> Popen[str]:
        args = [console_script] + args
        return Popen(args, text=True)

    return _inner


class OPCServer:
    def __init__(self) -> None:
        mydir = Path(__file__).resolve().parent
        self.log_file = open(mydir / "opc_server.log", "w")
        self.process = Popen(
            [sys.executable, str(mydir / "opc_server.py"), str(OPC_SERVER_HTTP_PORT)],
            stdout=self.log_file,
            stderr=STDOUT,
        )
        assert not self.ping(), "OPC-UA testing server already started"

    def _url(self, endpoint: str) -> str:
        root_url = URL.build(scheme="http", host="127.0.0.1", port=OPC_SERVER_HTTP_PORT)
        return str(root_url / endpoint)

    @property
    def ping_url(self) -> str:
        return self._url("ping")

    @property
    def api_url(self) -> str:
        return self._url("api")

    def ping(self) -> bool:
        try:
            resp = requests.get(self.ping_url)
            resp.raise_for_status()
        except requests.RequestException:
            return False
        else:
            return True

    def reset(self) -> None:
        resp = requests.delete(self.api_url)
        resp.raise_for_status()


@pytest.fixture(scope="session")
def opcserver() -> Generator[OPCServer, None, None]:
    opc_server = OPCServer()
    while not opc_server.ping():
        time.sleep(0.1)
    yield opc_server
    opc_server.process.terminate()
    opc_server.process.wait()
    opc_server.log_file.close()


def test_entrypoint(main_process: MainProcessFixture) -> None:
    process = main_process(["--help"])
    assert process.wait(timeout=5.0) == 0
