# telemetry_node fuzz targets

This directory is reserved for Rust fuzz harnesses (cargo-fuzz/libFuzzer) for the telemetry node.

Suggested first target:
- deserialize and validate random telemetry payloads against the same constraints as HTTP/QUIC ingress.
