"""Launch the MCP stdio server from this plugin checkout."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = 'jev-model'
MODULE = 'jev_model_router.mcp_server'


def main() -> int:
    os.environ.setdefault("JEV_PROVIDER", "local")
    uv = shutil.which("uv")
    if uv:
        return subprocess.call([uv, "run", "--project", str(ROOT), CLI, "mcp"], cwd=ROOT)
    src = ROOT / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    __import__(MODULE, fromlist=["run_mcp"]).run_mcp()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
