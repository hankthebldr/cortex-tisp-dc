from __future__ import annotations

from collections.abc import Iterable

from app.analytics.classification import is_internal


class Masker:
    def __init__(self) -> None:
        self._map: dict[str, str] = {}
        self._counter = 0

    def register(self, ips: Iterable[str]) -> None:
        for ip in ips:
            if ip and ip not in self._map and is_internal(ip):
                self._counter += 1
                self._map[ip] = f"ENDPOINT-{self._counter:02d}"

    def mask(self, ip: str) -> str:
        return self._map.get(ip, ip)

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self._map)
