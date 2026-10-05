#!/usr/bin/env bash
# Usage: ./run.sh [vocab file or dir] [read|write|view]
cd "$(dirname "$0")"
SOURCE=${1:-resources/vocab/quiz_1.txt}

uv run python -m v2.app "${2:-read}" -s "$SOURCE"
