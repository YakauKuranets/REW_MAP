from app.security.crypto import decrypt_secret, encrypt_secret
from app.threat_intel.target_matcher import TargetAutomaton


def test_encrypt_decrypt_roundtrip():
    secret = "SuperSensitivePassword123!"
    encrypted = encrypt_secret(secret)
    assert encrypted != secret
    assert decrypt_secret(encrypted) == secret


def test_aho_corasick_finds_multiple_targets_case_insensitive():
    automaton = TargetAutomaton(["example.com", "admin@example.com", "TOKEN-ABC"])
    text = "Dump contains ADMIN@EXAMPLE.COM and token-abc in one row"
    found = automaton.find_matches(text)
    assert "admin@example.com" in found
    assert "token-abc" in found
