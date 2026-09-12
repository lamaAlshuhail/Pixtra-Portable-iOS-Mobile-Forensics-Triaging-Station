#!/bin/bash

PORT=${PORT:-8080}
HOST="127.0.0.1"
RELOAD=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --port) PORT="$2"; shift 2 ;;
        --dev) RELOAD="--reload"; shift ;;
        --host) HOST="$2"; shift 2 ;;
        *) shift ;;
    esac
done

echo "+======================================+"
echo "|          Pixtra v0.1.0               |"
echo "|   Mobile Forensics Platform          |"
echo "+======================================+"
echo ""
echo "Starting on http://${HOST}:${PORT}"
echo "API docs:  http://${HOST}:${PORT}/docs"
echo ""

cd "$(dirname "$0")"
python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT" $RELOAD
