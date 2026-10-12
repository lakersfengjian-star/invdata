#!/bin/zsh
set -eu

PROJECT_ROOT="${0:A:h:h}"
cd "$PROJECT_ROOT"

if [[ -n "$(git status --porcelain)" ]]; then
  print -u2 "同步已停止：当前电脑有未提交修改。请先提交或暂存，再执行同步。"
  exit 2
fi

git fetch --prune origin
git pull --ff-only origin main
print "已安全同步到远程 main：$(git rev-parse --short HEAD)"
