#!/bin/sh
# Compatibility wrapper — the real build driver is now tools/build.py, which is
# sh-free and portable (Windows/macOS). Kept so `sh tools/adventure.sh build
# <game>` and `... run <game>` continue to work; prefer `python3 tools/build.py`.
exec python3 "$(dirname "$0")/build.py" "$@"
