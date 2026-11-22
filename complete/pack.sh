#!/usr/bin/env bash
# B-完整版 打包: 干净展品 tar.gz (无 bak/pycache/tmp)
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"          # L09 脚本目录锚定
VER="2026.11.19"
OUT="dist/memsteward-full-$VER.tar.gz"
mkdir -p dist
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/memsteward-full"
rsync -a --exclude='*.bak*' --exclude='__pycache__' --exclude='.pytest_cache'       --exclude='*.pyc' --exclude='dist'       src config MANIFEST.md MANUAL.md "$STAGE/memsteward-full/"
tar czf "$OUT" -C "$STAGE" memsteward-full
echo "打包完成: $OUT ($(stat -c%s "$OUT") 字节)"
tar tzf "$OUT" | head -20
echo "... 共 $(tar tzf "$OUT" | wc -l) 件"
