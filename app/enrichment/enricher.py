from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).parent
_KB_PATH = _HERE / "malware_kb.json"
_PUBLIC_PATH = _HERE / "public_ips.json"


@dataclass(frozen=True)
class Attribution:
    family: str
    actor: str
    kb_hit: bool


class Enricher:
    def __init__(self) -> None:
        self._kb: list[dict[str, str]] = json.loads(_KB_PATH.read_text())
        self._public_ips: dict[str, str] = json.loads(_PUBLIC_PATH.read_text())

    def attribute(self, threat_name: str) -> Attribution:
        name = (threat_name or "").lower()
        for entry in self._kb:
            if entry["match"] in name:
                return Attribution(family=entry["family"], actor=entry["actor"], kb_hit=True)
        clean = threat_name.strip() if threat_name else "Unknown threat"
        return Attribution(
            family=f"{clean} | Unattributed C2",
            actor="Requires TIM / Unit 42 lookup",
            kb_hit=False,
        )

    def public_label(self, ip: str) -> str | None:
        return self._public_ips.get(ip)


enricher = Enricher()
