"""Fake upsd serving the variables captured from a real APC BZ1500XLBI-BR."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

VARS = dict(
    line.split("\t", 1)
    for line in (Path(__file__).parent / "bz1500_vars.tsv").read_text().splitlines()
)
RW = {
    "battery.mfr.date",
    "driver.debug",
    "driver.flag.allow_killpower",
    "input.sensitivity",
    "input.transfer.high",
    "input.transfer.low",
    "ups.delay.shutdown",
}
CMDS = {
    "beeper.disable", "beeper.enable", "beeper.mute", "beeper.off", "beeper.on",
    "driver.killpower", "load.off", "load.off.delay", "shutdown.reboot", "shutdown.stop",
    "test.battery.start.deep", "test.battery.start.quick", "test.battery.stop",
    "test.panel.start", "test.panel.stop",
}


class FakeUpsd:
    def __init__(self) -> None:
        self.vars = dict(VARS)
        self.received: list[str] = []
        self.port = 0
        self.users = {"admin": "s3cret"}

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        user = password = None
        while line := (await reader.readline()).decode().strip():
            self.received.append(line)
            words = line.split(" ", 3)
            reply: list[str]
            if line == "LIST UPS":
                reply = ["BEGIN LIST UPS", 'UPS myups "Description unavailable"', "END LIST UPS"]
            elif words[:2] == ["LIST", "VAR"]:
                rows = [f'VAR myups {k} "{v}"' for k, v in self.vars.items()]
                reply = ["BEGIN LIST VAR myups", *rows, "END LIST VAR myups"]
            elif words[:2] == ["LIST", "RW"]:
                rows = [f'RW myups {k} "{self.vars.get(k, "")}"' for k in sorted(RW)]
                reply = ["BEGIN LIST RW myups", *rows, "END LIST RW myups"]
            elif words[:2] == ["LIST", "CMD"]:
                reply = ["BEGIN LIST CMD myups", *(f"CMD myups {c}" for c in sorted(CMDS)), "END LIST CMD myups"]
            elif words[0] == "USERNAME":
                user, reply = words[1], ["OK"]
            elif words[0] == "PASSWORD":
                password, reply = line.split(" ", 1)[1].strip('"'), ["OK"]
            elif words[0] in ("SET", "INSTCMD"):
                if self.users.get(user or "") != password:
                    reply = ["ERR ACCESS-DENIED"]
                elif words[0] == "INSTCMD":
                    reply = ["OK"] if words[2] in CMDS else ["ERR CMD-NOT-SUPPORTED"]
                else:
                    name, value = line.split(" ", 4)[3:5]
                    self.vars[name] = value.strip('"')
                    reply = ["OK"]
            else:
                reply = ["ERR UNKNOWN-COMMAND"]
            writer.write(("\n".join(reply) + "\n").encode())
            await writer.drain()
        writer.close()


@pytest.fixture
async def upsd(socket_enabled):
    fake = FakeUpsd()
    server = await asyncio.start_server(fake.handle, "127.0.0.1", 0)
    fake.port = server.sockets[0].getsockname()[1]
    yield fake
    server.close()
    await server.wait_closed()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
