#!/bin/sh
# Backward-compatible entry point retained for earlier deployment notes.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$script_dir/build_netlify_live.sh"
