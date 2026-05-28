"""Shared logger: writes timestamped lines to console + output/extraction_log.txt."""

import sys
from datetime import datetime
from pathlib import Path

_log_file: Path | None = None
_stage_label: str = ""


def init(output_dir: Path, stage: str = ""):
    global _log_file, _stage_label
    output_dir.mkdir(parents=True, exist_ok=True)
    _log_file = output_dir / "extraction_log.txt"
    _stage_label = stage
    _write(f"\n{'='*60}")
    _write(f"STAGE: {stage}  started {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _write(f"{'='*60}")


def log(msg: str, indent: int = 0):
    prefix = "  " * indent
    line = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}]  {prefix}{msg}"
    print(line)
    _write(line)


def warn(msg: str):
    line = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}]  WARNING: {msg}"
    print(line, file=sys.stderr)
    _write(line)


def error(msg: str):
    line = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}]  ERROR: {msg}"
    print(line, file=sys.stderr)
    _write(line)


def section(title: str):
    line = f"\n--- {title} ---"
    print(line)
    _write(line)


def _write(line: str):
    if _log_file:
        with _log_file.open("a") as f:
            f.write(line + "\n")
