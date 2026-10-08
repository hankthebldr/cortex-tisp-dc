from pathlib import Path

from app.analytics.runs import analyze
from app.parsers.threat_log import read_threat_log
from app.parsers.traffic_log import read_traffic_log

FIXTURES = Path(__file__).parent / "fixtures"


def _load():
    threat, _ = read_threat_log(FIXTURES / "sample_threat.csv")
    traffic, _ = read_traffic_log(FIXTURES / "sample_traffic.csv", sinkhole_ip="72.5.65.111")
    return threat, traffic


def test_analysis_against_fixtures():
    threat, traffic = _load()
    result = analyze(threat, traffic, sinkhole_ip="72.5.65.111")

    assert result.kpis["threat_events"] == 15
    # 7 sinkhole rows → 5 unique source IPs (10.0.0.10 and 10.0.0.55 each appear twice)
    assert result.kpis["sinkhole_endpoints"] == 5

    dests = {d.dest_ip: d for d in result.c2_destinations}
    assert dests["185.220.101.45"].hits == 4
    assert dests["185.220.101.45"].family == "NanoCore RAT"
    assert dests["185.220.101.45"].kb_hit is True
    assert dests["8.8.8.8"].is_public is True
    assert dests["8.8.8.8"].public_label == "Google Public DNS"

    talkers = {t.source_ip: t for t in result.top_talkers}
    assert talkers["10.0.0.10"].hits == 5
    assert talkers["10.0.0.10"].classification == "likely_infra"
    assert talkers["10.0.0.72"].classification == "internal_endpoint"

    sinkhole = {s.source_ip: s for s in result.sinkhole_endpoints}
    assert sinkhole["10.0.0.10"].also_talker is True
    assert sinkhole["10.0.0.200"].also_talker is False


def test_sort_order_is_by_hits_desc():
    threat, traffic = _load()
    result = analyze(threat, traffic, sinkhole_ip="72.5.65.111")
    hits = [d.hits for d in result.c2_destinations]
    assert hits == sorted(hits, reverse=True)
    talk_hits = [t.hits for t in result.top_talkers]
    assert talk_hits == sorted(talk_hits, reverse=True)


def test_declared_infra_overrides_heuristic():
    threat, _ = _load()
    result = analyze(threat, None, sinkhole_ip="72.5.65.111", declared_infra={"10.0.0.72"})
    talkers = {t.source_ip: t for t in result.top_talkers}
    assert talkers["10.0.0.72"].classification == "declared_infra"


def test_no_traffic_log_yields_empty_sinkhole():
    threat, _ = _load()
    result = analyze(threat, None, sinkhole_ip="72.5.65.111")
    assert result.sinkhole_endpoints == []
    assert result.kpis["sinkhole_endpoints"] == 0
