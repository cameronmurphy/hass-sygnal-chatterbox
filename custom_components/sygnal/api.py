"""JSON-RPC API client for the Sygnal Chatterbox Connect12."""

import asyncio
import logging

import aiohttp

from .const import ENDPOINT, MAX_FETCH

_LOGGER = logging.getLogger(__name__)


class SygnalApi:
    """HTTP client for the Chatterbox JSON-RPC interface."""

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        self._host = host
        self._session = session
        self._url = f"http://{host}{ENDPOINT}"
        self._write_lock = asyncio.Lock()
        self._seq = 1

    async def _rpc(self, method: str, params: dict) -> dict:
        """Send a JSON-RPC request and return the parsed response."""
        self._seq += 1
        payload = {"method": method, "params": [params], "id": self._seq}
        async with self._session.post(
            self._url, json=payload, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def fetch_table(
        self, table: str, start: int, length: int
    ) -> tuple[list[int], list[float]]:
        """Fetch a range of bytes from a table. Returns (values, ages)."""
        values: list[int] = []
        ages: list[float] = []
        offset = start
        remaining = length
        while remaining > 0:
            chunk = min(remaining, MAX_FETCH)
            data = await self._rpc(
                "fetch",
                {
                    "table": table,
                    "start": offset,
                    "length": chunk,
                    "marker": f"ha_{table}{offset}",
                    "datatype": "bytes",
                },
            )
            result = data.get("result", {})
            values.extend(result.get("values", []))
            ages.extend(result.get("age", []))
            offset += chunk
            remaining -= chunk
        return values, ages

    async def fetch_paray(self) -> list[int]:
        """Fetch the entire paray table (137 bytes)."""
        from .const import PARAY_SIZE

        values, _ = await self.fetch_table("paray", 0, PARAY_SIZE)
        return values

    async def fetch_ee(self, start: int = 0, length: int | None = None) -> list[int]:
        """Fetch from the EE table."""
        from .const import EE_SIZE

        if length is None:
            length = EE_SIZE
        values, _ = await self.fetch_table("ee", start, length)
        return values

    async def write_paray(self, offset: int, mask: int, value: int) -> None:
        """Write a masked value to a paray byte (CMD_ALTER_PARAM)."""
        async with self._write_lock:
            await self._rpc(
                "send_packet",
                {
                    "marker": "paw",
                    "cmd": 0,
                    "data": [offset, mask & 0xFF, value & 0xFF],
                },
            )

    async def write_ee_block(
        self, block_index: int, v0: int, v1: int, v2: int, v3: int
    ) -> None:
        """Write a 4-byte EE block (CMD_SET_EBLOCK)."""
        async with self._write_lock:
            await self._rpc(
                "send_packet",
                {
                    "marker": "eew",
                    "cmd": 7,
                    "data": [block_index, v0 & 0xFF, v1 & 0xFF, v2 & 0xFF, v3 & 0xFF],
                },
            )

    async def test_connection(self) -> bool:
        """Test connectivity by fetching the ID table."""
        try:
            values, _ = await self.fetch_table("id", 0, 4)
            return len(values) == 4
        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError):
            return False
