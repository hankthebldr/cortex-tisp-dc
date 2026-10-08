from __future__ import annotations

COLUMN_VARIANTS: dict[str, tuple[str, ...]] = {
    "source_ip": (
        "source address", "src", "source", "source_ip", "srcip", "source ip",
    ),
    "dest_ip": (
        "destination address", "dst", "destination", "dest",
        "destination_ip", "dstip", "destination ip",
    ),
    "threat_name": (
        "threat/content name", "threat name", "threat content name",
        "threatid", "threat id", "threat", "content name", "name",
    ),
    "severity": ("severity", "sev"),
    "subtype": ("subtype", "sub type", "type"),
}


def resolve_columns(headers: list[str], fields: list[str]) -> dict[str, str | None]:
    lowered = {h.lower().strip(): h for h in headers}
    out: dict[str, str | None] = {}
    for field in fields:
        variants = COLUMN_VARIANTS.get(field, ())
        matched: str | None = None
        for v in variants:
            if v in lowered:
                matched = lowered[v]
                break
        if matched is None:
            for v in variants:
                for low, original in lowered.items():
                    if v in low:
                        matched = original
                        break
                if matched is not None:
                    break
        out[field] = matched
    return out
