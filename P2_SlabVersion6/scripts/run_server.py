"""Start SDIE V6 web UI + API."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
os.chdir(ROOT)

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("SDIE_HOST", "127.0.0.1")
    port = int(os.environ.get("SDIE_PORT", "8765"))
    print(f"SDIE V6 — open http://{host}:{port}/")
    print(f"Project root: {ROOT}")
    uvicorn.run(
        "sdie.api.app:app",
        host=host,
        port=port,
        reload=False,
        timeout_keep_alive=600,
    )
