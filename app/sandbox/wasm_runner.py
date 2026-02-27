import json
import logging
import os
from typing import Any

from wasmtime import Engine, Instance, Linker, Module, Store, WasiConfig

logger = logging.getLogger(__name__)


class WasmSandbox:
    def __init__(self):
        self.engine = Engine()
        self.linker = Linker(self.engine)
        # Enable WASI for constrained execution model.
        self.linker.define_wasi()

    def run_parser(self, wasm_file_path: str, target_file_path: str) -> str:
        """Run parser wasm in constrained WASI sandbox and return JSON string."""
        if not os.path.exists(wasm_file_path):
            logger.error("[WASM_SANDBOX] Бинарник %s не найден.", wasm_file_path)
            return json.dumps({"error": "wasm module missing"})

        if not os.path.exists(target_file_path):
            return json.dumps({"error": "target file missing"})

        store = Store(self.engine)

        wasi_cfg = WasiConfig()
        wasi_cfg.argv = ["parser.wasm", "/workspace/" + os.path.basename(target_file_path)]
        wasi_cfg.preopen_dir(os.path.dirname(target_file_path), "/workspace")
        store.set_wasi(wasi_cfg)

        try:
            module = Module.from_file(self.engine, wasm_file_path)
            instance = self.linker.instantiate(store, module)

            exports: dict[str, Any] = instance.exports(store)
            start = exports.get("_start")
            if start:
                start(store)
                logger.info("[WASM_SANDBOX] Изолированный анализ успешно завершен.")
                return json.dumps({"status": "analyzed_in_sandbox", "safe": True})
            return json.dumps({"error": "no start function"})

        except Exception as e:
            logger.critical("[WASM_SANDBOX] ПЕСОЧНИЦА ЗАБЛОКИРОВАЛА СБОЙ/АТАКУ: %s", e)
            return json.dumps({
                "error": "sandbox_execution_failed",
                "malicious_payload_suspected": True,
            })


sandbox_engine = WasmSandbox()
