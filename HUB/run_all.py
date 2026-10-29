#!/usr/bin/env python3
"""Start the demo hub on http://127.0.0.1:<ports.hub> (builds the catalog first if missing).

    python run_all.py

Proof-of-concept scope: one process. Devices, cloud and LoRa relay are simulated inside the hub.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from common.config import load  # noqa: E402


def main() -> None:
    cfg = load()
    if not cfg["paths"]["catalog_db"].exists():
        print("catalog.sqlite missing: building it (about 10 s)...")
        subprocess.run([sys.executable, str(ROOT / "preprocess" / "build_catalog.py")], check=True, cwd=ROOT)
    import uvicorn

    port = int(cfg["ports"]["hub"])
    print(f"\n  Hub dashboard: http://127.0.0.1:{port}\n")
    uvicorn.run("hub.app:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
