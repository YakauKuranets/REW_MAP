from __future__ import annotations

from app.diagnostics.automotive.bus_analyzer import AutomotiveBusAnalyzer
from app.diagnostics.fiveg.relay_analyzer import RelaySecurityAnalyzer
from app.diagnostics.satellite.iridium_analyzer import IridiumSignalAnalyzer


def test_relay_analyzer_basic():
    analyzer = RelaySecurityAnalyzer()
    result = analyzer.analyze_relay_configuration("ue-1", "ABC123")
    assert result["security_level"] in {"high", "medium", "low"}
    assert analyzer.validate_key_derivation(b"k", b"n", b"f") is True


def test_iridium_analyzer_basic():
    analyzer = IridiumSignalAnalyzer()
    result = analyzer.analyze_signal()
    assert result["protocol_version"] in {"first_gen", "second_gen", "unknown"}
    loc = analyzer.locate_device("dev")
    assert "latitude" in loc and "longitude" in loc


def test_automotive_bus_analyzer_basic():
    analyzer = AutomotiveBusAnalyzer(interface="can0")
    lin = analyzer.analyze_lin_bus(duration=3)
    flex = analyzer.analyze_flexray(duration=4)
    assert lin["protocol"] == "LIN"
    assert flex["protocol"] == "FlexRay"
