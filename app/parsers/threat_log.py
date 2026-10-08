from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd

from app.parsers.column_resolver import resolve_columns

SEVERITY_SET = {"medium", "high", "critical"}
NORMALIZED_COLS = ["source_ip", "dest_ip", "threat_name", "severity", "subtype"]


def read_threat_log(source: str | Path | StringIO) -> tuple[pd.DataFrame, dict[str, str | None]]:
    df = pd.read_csv(source, dtype=str, keep_default_na=False)
    cols = resolve_columns(list(df.columns), NORMALIZED_COLS)

    rename_map = {v: k for k, v in cols.items() if v is not None}
    normalized = df.rename(columns=rename_map)

    for logical in NORMALIZED_COLS:
        if logical not in normalized.columns:
            normalized[logical] = ""

    normalized["severity"] = normalized["severity"].str.lower().str.strip()
    normalized["subtype"] = normalized["subtype"].str.lower().str.strip()

    filtered = normalized[
        normalized["subtype"].str.contains("spyware", na=False)
        & normalized["severity"].isin(SEVERITY_SET)
    ]

    effective = filtered if not filtered.empty else normalized
    return effective.reset_index(drop=True), cols
