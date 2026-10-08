from __future__ import annotations

import ipaddress
from typing import Literal

INFRA_HOST_OCTETS = {1, 2, 10, 11, 53}

Classification = Literal["declared_infra", "likely_infra", "internal_endpoint", "external"]


def classify_source(ip: str, declared_infra: set[str]) -> Classification:
    if ip in declared_infra:
        return "declared_infra"
    try:
        addr = ipaddress.ip_address(ip)
    except (ValueError, TypeError):
        return "external"
    if not addr.is_private:
        return "external"
    last_octet = int(ip.split(".")[-1])
    if last_octet in INFRA_HOST_OCTETS:
        return "likely_infra"
    return "internal_endpoint"


def is_internal(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except (ValueError, TypeError):
        return False
