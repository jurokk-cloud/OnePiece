#!/usr/bin/env bash
# Project verification: lint + tests + docs. The venv must live off the NTFS
# mount (see CONTRIBUTING.md); default location is ~/.venvs/onepiece.
set -euo pipefail

PY="${ONEPIECE_VENV:-$HOME/.venvs/onepiece}/bin/python"

if [[ ! -x "$PY" ]]; then
    echo "error: venv python not found at $PY" >&2
    echo "Create the venv off the NTFS mount (see CONTRIBUTING.md) or set ONEPIECE_VENV." >&2
    exit 1
fi

"$PY" -m ruff check src tests ui/src
"$PY" -m pytest --tb=short -q

# Docs gate: -W turns warnings (orphaned pages, broken refs, duplicate
# toctree entries) into errors. Build off the NTFS mount for speed.
DOCS_BUILD="$(mktemp -d)"
trap 'rm -rf "$DOCS_BUILD"' EXIT
"$PY" -m sphinx -b html -W -q docs/source "$DOCS_BUILD"
