#!/usr/bin/env bash
# Usage: ./run.sh [vocab file or dir] [read|write]
cd "$(dirname "$0")"
SOURCE=${1:-resources/vocab/quiz_1.txt}

uv run python -m src.test -s "$SOURCE" "${@:2}"