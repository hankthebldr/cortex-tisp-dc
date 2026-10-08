from app.enrichment.enricher import enricher


def test_known_threat_hits_kb():
    attr = enricher.attribute("NanoCore RAT Command and Control Traffic Detection")
    assert attr.family == "NanoCore RAT"
    assert attr.kb_hit is True


def test_unknown_threat_falls_back():
    attr = enricher.attribute("Totally Novel Threat Variant 2026")
    assert "Unattributed C2" in attr.family
    assert "TIM" in attr.actor
    assert attr.kb_hit is False


def test_public_ip_label():
    assert enricher.public_label("8.8.8.8") == "Google Public DNS"
    assert enricher.public_label("1.1.1.1") == "Cloudflare DNS"


def test_private_ip_has_no_public_label():
    assert enricher.public_label("10.0.0.10") is None
