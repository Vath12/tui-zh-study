#!/usr/bin/env bash
# Usage: ./run.sh [vocab file or dir] [read|write|view]
cd "$(dirname "$0")"

uv run python -m src.app.proto
