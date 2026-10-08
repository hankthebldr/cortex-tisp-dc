from app.masking.tokenizer import Masker


def test_tokens_are_deterministic_in_order():
    m = Masker()
    m.register(["10.0.0.10", "10.0.0.55", "10.0.0.72"])
    assert m.mask("10.0.0.10") == "ENDPOINT-01"
    assert m.mask("10.0.0.55") == "ENDPOINT-02"
    assert m.mask("10.0.0.72") == "ENDPOINT-03"


def test_duplicate_registration_is_idempotent():
    m = Masker()
    m.register(["10.0.0.10"])
    m.register(["10.0.0.10", "10.0.0.11"])
    assert m.mask("10.0.0.10") == "ENDPOINT-01"
    assert m.mask("10.0.0.11") == "ENDPOINT-02"


def test_external_ips_are_not_masked():
    m = Masker()
    m.register(["8.8.8.8", "10.0.0.10"])
    assert m.mask("8.8.8.8") == "8.8.8.8"
    assert m.mask("10.0.0.10") == "ENDPOINT-01"


def test_unknown_ip_passes_through():
    m = Masker()
    assert m.mask("172.16.0.5") == "172.16.0.5"
