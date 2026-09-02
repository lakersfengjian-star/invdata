#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h}"
PYTHON_BIN="${INVDATA_PYTHON:-/opt/anaconda3/envs/invdata/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  print -u2 "Python environment not found: $PYTHON_BIN"
  exit 1
fi

cd "$PROJECT_ROOT"

WIND_NODE_DIR="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin"
export PATH="$WIND_NODE_DIR:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONUNBUFFERED=1
export PYTHONPYCACHEPREFIX=/tmp/codex-pycache
export MPLCONFIGDIR="$PROJECT_ROOT/.work/cache/matplotlib"
export INVDATA_RUN_CWD="$PROJECT_ROOT"

mkdir -p "$MPLCONFIGDIR"
"$PYTHON_BIN" -u scripts/run_scheduled_updates.py --mode scheduled
"$SCRIPT_DIR/deploy_mainland_site.sh"
