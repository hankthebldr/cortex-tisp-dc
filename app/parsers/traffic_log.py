from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd

from app.parsers.column_resolver import resolve_columns

NORMALIZED_COLS = ["source_ip", "dest_ip"]


def read_traffic_log(
    source: str | Path | StringIO, sinkhole_ip: str
) -> tuple[pd.DataFrame, dict[str, str | None]]:
    df = pd.read_csv(source, dtype=str, keep_default_na=False)
    cols = resolve_columns(list(df.columns), NORMALIZED_COLS)

    rename_map = {v: k for k, v in cols.items() if v is not None}
    normalized = df.rename(columns=rename_map)

    for logical in NORMALIZED_COLS:
        if logical not in normalized.columns:
            normalized[logical] = ""

    normalized["source_ip"] = normalized["source_ip"].str.strip()
    normalized["dest_ip"] = normalized["dest_ip"].str.strip()

    filtered = normalized[normalized["dest_ip"] == sinkhole_ip]
    effective = filtered if not filtered.empty else normalized
    return effective.reset_index(drop=True), cols
