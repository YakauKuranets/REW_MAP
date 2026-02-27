from __future__ import annotations

import os
from pathlib import Path


def load_dotenv_like(*candidates: str) -> str | None:
    """Minimal .env loader (no dependencies).

    Loads KEY=VALUE lines into os.environ if key is not already set.
    Returns the path that was loaded, or None if nothing found.
    """
    paths: list[Path] = []
    for c in candidates:
        if c:
            paths.append(Path(c))

    cwd = Path.cwd()
    # project root assumed to be folder containing this file
    proj_root = Path(__file__).resolve().parent

    paths.extend([cwd/".env", proj_root/".env", cwd/".env.local", proj_root/".env.local"])

    for p in paths:
        try:
            if not p.exists() or not p.is_file():
                continue
            for raw in p.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if not k:
                    continue
                os.environ.setdefault(k, v)
            return str(p)
        except Exception:
            continue
    return None
