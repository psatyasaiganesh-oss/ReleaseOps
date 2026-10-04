#!/usr/bin/env python3
"""Consistent SQLite backup using the online backup API, including WAL writes."""
import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("database", type=Path)
parser.add_argument("destination", type=Path)
args = parser.parse_args()
if not args.database.is_file():
    raise SystemExit("Source database does not exist")
if args.database.resolve() == args.destination.resolve() or args.destination.exists():
    raise SystemExit("Choose a new backup path distinct from the source database")
args.destination.parent.mkdir(parents=True, exist_ok=True)
temporary = args.destination.with_suffix(args.destination.suffix + ".tmp")
if temporary.exists():
    raise SystemExit("Temporary backup file exists; choose another destination")
try:
    with closing(sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(temporary)) as target:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise SystemExit("Backup failed integrity check")
    os.chmod(temporary, 0o600)
    os.replace(temporary, args.destination)
finally:
    temporary.unlink(missing_ok=True)
print(f"Backup complete: {args.destination}")
