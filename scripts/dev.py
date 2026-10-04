#!/usr/bin/env python3
"""Portable local startup. Save the operator token without printing it."""
import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8080)
parser.add_argument("--demo", action="store_true")
args = parser.parse_args()
local = root / ".local"
local.mkdir(mode=0o700, exist_ok=True)
token_file = local / "dev-token"
if not token_file.exists():
    token_file.write_text(secrets.token_urlsafe(32))
token_file.chmod(0o600)
env = dict(os.environ, API_TOKEN=token_file.read_text().strip(), APP_ENV="development",
           DATABASE_PATH=str(local / "releaseops.db"), FAILURE_FILE=str(local / "unhealthy"))
print(f"Open http://localhost:{args.port}. Operator token: .local/dev-token", flush=True)
command = [sys.executable, "-m", "releaseops.server", "--port", str(args.port)]
if args.demo:
    command.append("--demo")
try:
    raise SystemExit(subprocess.call(command, cwd=root, env=env))
except KeyboardInterrupt:
    pass
