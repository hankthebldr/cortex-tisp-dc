from io import StringIO
from pathlib import Path

from app.parsers.column_resolver import resolve_columns
from app.parsers.threat_log import read_threat_log
from app.parsers.traffic_log import read_traffic_log

FIXTURES = Path(__file__).parent / "fixtures"


def test_column_resolver_exact_match():
    cols = resolve_columns(
        ["Source address", "Destination address", "Severity", "Subtype", "Threat/Content Name"],
        ["source_ip", "dest_ip", "severity", "subtype", "threat_name"],
    )
    assert cols["source_ip"] == "Source address"
    assert cols["dest_ip"] == "Destination address"
    assert cols["threat_name"] == "Threat/Content Name"


def test_column_resolver_substring_fallback():
    cols = resolve_columns(
        ["my srcip field", "my dstip field"],
        ["source_ip", "dest_ip"],
    )
    assert cols["source_ip"] == "my srcip field"
    assert cols["dest_ip"] == "my dstip field"


def test_column_resolver_missing():
    cols = resolve_columns(["unrelated"], ["source_ip"])
    assert cols["source_ip"] is None


def test_threat_log_fixture_applies_filter():
    df, cols = read_threat_log(FIXTURES / "sample_threat.csv")
    assert len(df) == 15
    assert set(df["severity"].unique()).issubset({"medium", "high", "critical"})
    assert (df["subtype"] == "spyware").all()
    assert cols["source_ip"] == "Source address"


def test_threat_log_handles_prefiltered():
    csv = (
        "Source address,Destination address,Threat/Content Name,Severity,Subtype\n"
        "10.0.0.1,1.2.3.4,X,info,other\n"
    )
    df, _ = read_threat_log(StringIO(csv))
    assert len(df) == 1


def test_traffic_log_filters_to_sinkhole():
    df, _ = read_traffic_log(FIXTURES / "sample_traffic.csv", sinkhole_ip="72.5.65.111")
    assert len(df) == 7
    assert (df["dest_ip"] == "72.5.65.111").all()


def test_traffic_log_with_wrong_sinkhole_falls_back():
    df, _ = read_traffic_log(FIXTURES / "sample_traffic.csv", sinkhole_ip="9.9.9.9")
    assert len(df) == 7
