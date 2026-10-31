#!/bin/sh
# Retro Visual Novel — reuse the fighter's proven harness.
# (copy of ../the-arousa-job/tools/spectrum.sh; python file kept in sync)
# usage: sh tools/adventure.sh harness <command> [args...]
#   e.g. sh tools/adventure.sh harness run "$(pwd)/adventure.tap"
exec python3 "$(dirname "$0")/spectrum.py" "$@"