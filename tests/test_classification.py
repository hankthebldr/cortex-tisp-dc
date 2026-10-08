from app.analytics.classification import classify_source, is_internal


def test_declared_infra_wins():
    assert classify_source("10.0.0.200", {"10.0.0.200"}) == "declared_infra"


def test_likely_infra_heuristic():
    assert classify_source("10.0.0.10", set()) == "likely_infra"
    assert classify_source("192.168.1.53", set()) == "likely_infra"


def test_internal_endpoint():
    assert classify_source("10.0.0.72", set()) == "internal_endpoint"


def test_external():
    assert classify_source("8.8.8.8", set()) == "external"


def test_is_internal_rfc1918():
    assert is_internal("10.0.0.1") is True
    assert is_internal("172.20.5.5") is True
    assert is_internal("192.168.0.1") is True
    assert is_internal("8.8.8.8") is False
    assert is_internal("not-an-ip") is False
