from __future__ import annotations

from celery import shared_task

from app.diagnostics.models import DiagnosticTarget
from app.extensions import db


@shared_task(name="app.tasks.diagnostics_scans.run_mqtt_scan")
def run_mqtt_scan(target_id: int, ip: str, port: int = 1883, username: str | None = None, password: str | None = None):
    """Run inventory-style MQTT availability check and persist result."""
    _ = (username, password)
    target = DiagnosticTarget.query.get(target_id)
    if not target:
        return {"ok": False, "error": "target_not_found"}

    from app.diagnostics.industrial.mqtt_broker_check import MQTTBrokerCheck

    analyzer = MQTTBrokerCheck()
    result = analyzer.check(ip, int(port))
    target.result = result
    target.status = "completed"
    db.session.add(target)
    db.session.commit()
    return {"ok": True, "target_id": target_id, "result": result}


@shared_task(name="app.tasks.diagnostics_scans.run_profinet_scan")
def run_profinet_scan(target_id: int, interface: str = "eth0"):
    """Run Profinet DCP discovery and persist discovered devices."""
    target = DiagnosticTarget.query.get(target_id)
    if not target:
        return {"ok": False, "error": "target_not_found"}

    from app.diagnostics.industrial.profinet_analyzer import ProfinetAnalyzer

    analyzer = ProfinetAnalyzer(interface=interface)
    devices = analyzer.discover_devices()
    target.result = {"devices": devices, "count": len(devices)}
    target.status = "completed"
    db.session.add(target)
    db.session.commit()
    return {"ok": True, "target_id": target_id, "devices": len(devices)}


@shared_task(name="app.tasks.diagnostics_scans.run_lorawan_monitor")
def run_lorawan_monitor(target_id: int, duration: int = 60):
    """Run LoRaWAN passive monitor and persist captured packet metadata."""
    target = DiagnosticTarget.query.get(target_id)
    if not target:
        return {"ok": False, "error": "target_not_found"}

    from app.diagnostics.iot.lorawan_monitor import LoRaWANMonitor

    monitor = LoRaWANMonitor()
    started = monitor.start_monitor(duration=max(1, int(duration)))
    packets = monitor.parse_results() if started else []
    if started:
        try:
            monitor.stop_monitor()
        except Exception:
            pass

    target.result = {"packets": packets, "count": len(packets), "started": bool(started)}
    target.status = "completed"
    db.session.add(target)
    db.session.commit()
    return {"ok": True, "target_id": target_id, "packets": len(packets), "started": bool(started)}


@shared_task(name="app.tasks.diagnostics_scans.run_5g_relay_scan")
def run_5g_relay_scan(target_id: int, remote_ue_id: str, relay_service_code: str):
    """Run 5G relay security configuration analysis and persist result."""
    target = DiagnosticTarget.query.get(target_id)
    if not target:
        return {"ok": False, "error": "target_not_found"}

    from app.diagnostics.fiveg.relay_analyzer import RelaySecurityAnalyzer

    analyzer = RelaySecurityAnalyzer()
    result = analyzer.analyze_relay_configuration(remote_ue_id=remote_ue_id, relay_service_code=relay_service_code)
    target.result = result
    target.status = "completed"
    db.session.add(target)
    db.session.commit()
    return {"ok": True, "target_id": target_id, "security_level": result.get("security_level")}


@shared_task(name="app.tasks.diagnostics_scans.run_iridium_scan")
def run_iridium_scan(target_id: int, frequency: float = 1616e6):
    """Run Iridium signature analysis and persist result."""
    target = DiagnosticTarget.query.get(target_id)
    if not target:
        return {"ok": False, "error": "target_not_found"}

    from app.diagnostics.satellite.iridium_analyzer import IridiumSignalAnalyzer

    analyzer = IridiumSignalAnalyzer()
    result = analyzer.analyze_signal(frequency=float(frequency))
    target.result = result
    target.status = "completed"
    db.session.add(target)
    db.session.commit()
    return {"ok": True, "target_id": target_id, "protocol": result.get("protocol_version")}


@shared_task(name="app.tasks.diagnostics_scans.run_automotive_bus_scan")
def run_automotive_bus_scan(target_id: int, interface: str = "can0", protocol: str = "lin"):
    """Run automotive LIN/FlexRay analyzer and persist result."""
    target = DiagnosticTarget.query.get(target_id)
    if not target:
        return {"ok": False, "error": "target_not_found"}

    from app.diagnostics.automotive.bus_analyzer import AutomotiveBusAnalyzer

    analyzer = AutomotiveBusAnalyzer(interface=interface)
    proto = (protocol or "lin").strip().lower()
    if proto == "flexray":
        result = analyzer.analyze_flexray()
    else:
        result = analyzer.analyze_lin_bus()

    target.result = {"interface": interface, "protocol": proto, "analysis": result}
    target.status = "completed"
    db.session.add(target)
    db.session.commit()
    return {"ok": True, "target_id": target_id, "protocol": proto}
