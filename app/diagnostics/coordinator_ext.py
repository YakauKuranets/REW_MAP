from __future__ import annotations

from typing import Any

from app.diagnostics.coordinator import TaskCoordinator


class ExtendedTaskCoordinator(TaskCoordinator):
    """Расширение планировщика: добавляет IoT/OT/Auto категории."""

    def plan_tasks(self, target: Any) -> list[dict[str, Any]]:
        base = super().plan_tasks(target)
        t = (getattr(target, "type", "") or "").lower()
        identifier = getattr(target, "identifier", "")

        extra: list[dict[str, Any]] = []
        if t == "zigbee":
            extra.append({"type": "zigbee_scan", "priority": 5, "params": {"target": identifier}})
        elif t == "zwave":
            extra.append({"type": "zwave_scan", "priority": 5, "params": {"target": identifier}})
        elif t == "lorawan":
            extra.append({"type": "lorawan_monitor", "priority": 5, "params": {"target": identifier}})
            extra.append({"type": "run_lorawan_monitor", "priority": 6, "params": {"duration": 60}})
        elif t == "modbus":
            extra.append({"type": "modbus_scan", "priority": 5, "params": {"target": identifier}})
        elif t == "mqtt":
            extra.append({"type": "mqtt_check", "priority": 5, "params": {"target": identifier}})
            extra.append({"type": "run_mqtt_scan", "priority": 6, "params": {"ip": identifier, "port": 1883}})
        elif t == "profinet":
            extra.append({"type": "run_profinet_scan", "priority": 5, "params": {"interface": "eth0"}})
        elif t in {"5g", "5g_relay", "relay_5g"}:
            extra.append({"type": "run_5g_relay_scan", "priority": 5, "params": {"remote_ue_id": identifier, "relay_service_code": "ABC123"}})
        elif t in {"iridium", "satellite"}:
            extra.append({"type": "run_iridium_scan", "priority": 5, "params": {"frequency": 1616000000.0}})
        elif t in {"lin", "flexray", "automotive_bus"}:
            proto = "flexray" if t == "flexray" else "lin"
            extra.append({"type": "run_automotive_bus_scan", "priority": 5, "params": {"interface": "can0", "protocol": proto}})
        elif t == "can":
            extra.append({"type": "can_inspect", "priority": 5, "params": {"target": identifier}})

        return sorted([*base, *extra], key=lambda x: int(x.get("priority", 100)))
