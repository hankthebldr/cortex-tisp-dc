from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd

from app.analytics.classification import Classification, classify_source
from app.enrichment.enricher import enricher

SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1}


@dataclass
class C2Destination:
    dest_ip: str
    hits: int
    primary_threat: str
    top_severity: str
    family: str
    actor: str
    kb_hit: bool
    public_label: str | None
    is_public: bool


@dataclass
class TopTalker:
    source_ip: str
    hits: int
    classification: Classification


@dataclass
class SinkholeEndpoint:
    source_ip: str
    hits: int
    also_talker: bool


@dataclass
class AnalysisResult:
    c2_destinations: list[C2Destination] = field(default_factory=list)
    top_talkers: list[TopTalker] = field(default_factory=list)
    sinkhole_endpoints: list[SinkholeEndpoint] = field(default_factory=list)
    kpis: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "c2_destinations": [asdict(d) for d in self.c2_destinations],
            "top_talkers": [asdict(t) for t in self.top_talkers],
            "sinkhole_endpoints": [asdict(s) for s in self.sinkhole_endpoints],
            "kpis": self.kpis,
        }


def _top_severity(series: pd.Series) -> str:
    ranked = series.map(SEVERITY_RANK).fillna(0)
    if ranked.max() == 0:
        return ""
    best_idx = ranked.idxmax()
    return str(series.loc[best_idx])


def run1_c2_enrichment(threat_df: pd.DataFrame) -> list[C2Destination]:
    if threat_df.empty:
        return []
    out: list[C2Destination] = []
    grouped = threat_df.groupby("dest_ip", sort=False)
    for dest_ip, group in grouped:
        if not dest_ip:
            continue
        primary = str(group["threat_name"].iloc[0]) if not group["threat_name"].empty else ""
        attr = enricher.attribute(primary)
        label = enricher.public_label(dest_ip)
        out.append(
            C2Destination(
                dest_ip=dest_ip,
                hits=int(len(group)),
                primary_threat=primary,
                top_severity=_top_severity(group["severity"]),
                family=attr.family,
                actor=attr.actor,
                kb_hit=attr.kb_hit,
                public_label=label,
                is_public=label is not None,
            )
        )
    out.sort(key=lambda d: d.hits, reverse=True)
    return out


def run2_top_talkers(threat_df: pd.DataFrame, declared_infra: set[str]) -> list[TopTalker]:
    if threat_df.empty:
        return []
    counts = threat_df.groupby("source_ip", sort=False).size()
    talkers = [
        TopTalker(
            source_ip=str(ip),
            hits=int(hits),
            classification=classify_source(str(ip), declared_infra),
        )
        for ip, hits in counts.items()
        if ip
    ]
    talkers.sort(key=lambda t: t.hits, reverse=True)
    return talkers


def run3_sinkhole_correlation(
    traffic_df: pd.DataFrame, sinkhole_ip: str, talker_ips: set[str]
) -> list[SinkholeEndpoint]:
    if traffic_df.empty:
        return []
    sinkhole_rows = traffic_df[traffic_df["dest_ip"] == sinkhole_ip]
    if sinkhole_rows.empty:
        return []
    counts = sinkhole_rows.groupby("source_ip", sort=False).size()
    endpoints = [
        SinkholeEndpoint(
            source_ip=str(ip),
            hits=int(hits),
            also_talker=str(ip) in talker_ips,
        )
        for ip, hits in counts.items()
        if ip
    ]
    endpoints.sort(key=lambda e: e.hits, reverse=True)
    return endpoints


def analyze(
    threat_df: pd.DataFrame,
    traffic_df: pd.DataFrame | None,
    sinkhole_ip: str,
    declared_infra: set[str] | None = None,
) -> AnalysisResult:
    declared = declared_infra or set()
    c2 = run1_c2_enrichment(threat_df)
    talkers = run2_top_talkers(threat_df, declared)
    talker_ips = {t.source_ip for t in talkers}
    sinkhole = (
        run3_sinkhole_correlation(traffic_df, sinkhole_ip, talker_ips)
        if traffic_df is not None
        else []
    )
    kpis = {
        "threat_events": int(len(threat_df)) if threat_df is not None else 0,
        "unique_destinations": len(c2),
        "unique_sources": len(talkers),
        "sinkhole_endpoints": len(sinkhole),
        "active_infections": sum(1 for s in sinkhole if s.also_talker),
        "public_dest_hits": sum(1 for d in c2 if d.is_public),
    }
    return AnalysisResult(
        c2_destinations=c2,
        top_talkers=talkers,
        sinkhole_endpoints=sinkhole,
        kpis=kpis,
    )
