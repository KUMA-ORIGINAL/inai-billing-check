#!/usr/bin/env sh
# One command for Linux/macOS: runs analyze.py with Python 3.10+.
# Standard library only: no installation and no internet needed.
# Usage:  ./run.sh [billing.csv ...] [--open] [--serve] [--llm] [other analyze.py options]
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"
elif [ -x "$ROOT/.venv/Scripts/python.exe" ]; then PY="$ROOT/.venv/Scripts/python.exe"  # Git Bash
elif command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else
    echo "Python 3.10+ not found. Install it from https://www.python.org and run again." >&2
    exit 3
fi
exec "$PY" "$ROOT/analyze.py" "$@"
