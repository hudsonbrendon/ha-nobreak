"""Minimal async client for the NUT network protocol (upsd).

The core ``aionut`` library has no LIST RW / SET VAR, so this speaks the
line protocol directly: one short TCP session per call, replies parsed with
``shlex`` (upsd quotes values and backslash-escapes ``"`` and ``\\``).
"""

from __future__ import annotations

import asyncio
import contextlib
import shlex


class NutError(Exception):
    """upsd answered ERR or the connection failed."""


def _quote(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise NutError("INVALID-ARGUMENT")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _name(value: str) -> str:
    # ups/var/command names go unquoted, so they must be a single safe token
    if not value or any(c.isspace() or c in '"\\' for c in value):
        raise NutError("INVALID-ARGUMENT")
    return value


class NutClient:
    """Talk to one upsd server."""

    def __init__(
        self,
        host: str,
        port: int = 3493,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout

    async def _readline(self, reader: asyncio.StreamReader) -> list[str]:
        try:
            raw = await asyncio.wait_for(reader.readline(), self.timeout)
        except TimeoutError as err:
            raise NutError("timeout waiting for upsd") from err
        if not raw:
            raise NutError("upsd closed the connection")
        parts = shlex.split(raw.decode("utf-8", "replace"))
        if not parts:
            raise NutError("empty reply from upsd")
        if parts[0] == "ERR":
            raise NutError(" ".join(parts[1:]) or "ERR")
        return parts

    async def _exchange(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, line: str
    ) -> list[list[str]]:
        writer.write(line.encode() + b"\n")
        await writer.drain()
        first = await self._readline(reader)
        if first[0] != "BEGIN":
            return [first]
        rows = []
        while (row := await self._readline(reader))[0] != "END":
            rows.append(row)
        return rows

    async def _session(self, *lines: str, auth: bool = False) -> list[list[list[str]]]:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        except (OSError, TimeoutError) as err:
            raise NutError(f"cannot connect to {self.host}:{self.port}: {err}") from err
        try:
            if auth:
                if not self.username or not self.password:
                    raise NutError("USERNAME-REQUIRED")
                await self._exchange(reader, writer, f"USERNAME {_name(self.username)}")
                await self._exchange(reader, writer, f"PASSWORD {_quote(self.password)}")
            return [await self._exchange(reader, writer, line) for line in lines]
        except OSError as err:
            raise NutError(str(err)) from err
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def list_ups(self) -> dict[str, str]:
        """Return {ups name: description}."""
        (rows,) = await self._session("LIST UPS")
        return {r[1]: r[2] if len(r) > 2 else "" for r in rows}

    async def list_vars(self, ups: str) -> dict[str, str]:
        (rows,) = await self._session(f"LIST VAR {_name(ups)}")
        return {r[2]: r[3] for r in rows if len(r) > 3}

    async def snapshot(self, ups: str) -> tuple[dict[str, str], set[str], set[str]]:
        """Variables, writable variable names and instant commands in one session."""
        ups = _name(ups)
        var, rw, cmd = await self._session(
            f"LIST VAR {ups}", f"LIST RW {ups}", f"LIST CMD {ups}"
        )
        return (
            {r[2]: r[3] for r in var if len(r) > 3},
            {r[2] for r in rw if len(r) > 2},
            {r[2] for r in cmd if len(r) > 2},
        )

    async def set_var(self, ups: str, name: str, value: str) -> None:
        await self._session(
            f"SET VAR {_name(ups)} {_name(name)} {_quote(value)}", auth=True
        )

    async def run_command(self, ups: str, command: str) -> None:
        await self._session(f"INSTCMD {_name(ups)} {_name(command)}", auth=True)
