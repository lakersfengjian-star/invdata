#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h}"
DEPLOY_HOST="${INVDATA_DEPLOY_HOST:-81.70.11.10}"
DEPLOY_USER="${INVDATA_DEPLOY_USER:-ubuntu}"
DEPLOY_ROOT="${INVDATA_DEPLOY_ROOT:-/var/www/research.fj.cn}"
SSH_KEY="${INVDATA_DEPLOY_KEY:-$HOME/.ssh/id_ed25519_tencent_lighthouse}"

if [[ ! -f "$SSH_KEY" ]]; then
  print -u2 "Deployment key not found: $SSH_KEY"
  exit 1
fi

cd "$PROJECT_ROOT"
rsync -az --delete \
  -e "ssh -i $SSH_KEY -o BatchMode=yes -o ConnectTimeout=15" \
  site/ "$DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_ROOT/"
ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=15 \
  "$DEPLOY_USER@$DEPLOY_HOST" \
  "find '$DEPLOY_ROOT' -type d -exec chmod 755 {} +; find '$DEPLOY_ROOT' -type f -exec chmod 644 {} +"
print "Published site to https://research.fj.cn"
