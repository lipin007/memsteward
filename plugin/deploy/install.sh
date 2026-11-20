#!/usr/bin/env bash
# MemSteward 商用精简版 · 一键安装器 v1（M2 deploy 脚手架）
#
# 用法：bash install.sh [--home <数据家>] [--port <端口>] [--skip-unit]
# 动作：装包（plugins.install）→ 起守护（systemd memt-daemon）→ 接线（gate 配置）→ 自检
# 铁则：家在 /home 分区独立门户（~/.memsteward），禁根分区辖地（/、/tmp、/var、/opt）
# 对偶：deploy/uninstall.sh（T0 账本永不删——卸载不删记忆）
set -euo pipefail

MEM_HOME="${MEM_HOME:-$HOME/.memsteward}"
PORT="${MEM_PORT:-8877}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
TGZ="$HERE/dist/memgate-2026.11.19.tgz"

echo "== MemSteward 安装器 v1 =="
echo "数据家: $MEM_HOME · 端口: $PORT · 包: $TGZ"

# ① 立家（家目录规范 v1：含生态位 modules/ packs/）
echo "== ① 立家（MemSteward 家目录规范 v1）=="
mkdir -p "$MEM_HOME"/{landing,products,plugins,state,shadow,config,tmp}  # 家目录规范 v2(2026-11-19 定名批: landing/products 角色名)
[ -f "$MEM_HOME/README.md" ] || cp "$HERE/deploy/home-spec.md" "$MEM_HOME/README.md" && echo "ok: 家目录规范已落位（README.md）"
[ -f "$MEM_HOME/家/landing.json" ] && echo "ok: T0 账本在位（$(python3 -c "import json;print(len(json.load(open('$MEM_HOME/家/landing.json')).get('entries',{})))" 2>/dev/null || echo '?') 条）——不覆盖" || echo "ok: 新家（账本首跑时自建）"

# ② 装包（插件注册）
echo "== ② 装包 =="
if [ "${MEM_SKIP_INSTALL:-0}" = "1" ]; then
  echo "skip: 测试模式（MEM_SKIP_INSTALL=1）"
elif command -v openclaw >&2 2>&1 && [ -f "$TGZ" ]; then
  openclaw plugins install "$TGZ" && echo "ok: 包已装（plugins.install）"
else
  echo "skip: 无 openclaw CLI 或包不在——开发链装（plugins.load.paths 指向 $HERE）"
fi

# ③ 守护单元（正式 systemd，开机自启）
echo "== ③ 守护单元 =="
if [ "${MEM_SKIP_UNIT:-0}" != "1" ]; then
  UNIT="$HOME/.config/systemd/user/memt-daemon.service"
  mkdir -p "$HOME/.config/systemd/user"
  sed "s|--landing [^ ]*landing.json|--landing $MEM_HOME/家/landing.json|; s|--port [0-9]*|--port $PORT|" \
      "$HERE/../记忆体/daemon/memt-daemon.service" > "$UNIT" 2>/dev/null || {
    cat > "$UNIT" <<UNIT_EOF
[Unit]
Description=MemSteward 记忆体 daemon
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/python3 $HERE/src/bridge_cli.py serve --landing $MEM_HOME/家/landing.json --port $PORT
Restart=on-failure
RestartSec=3
[Install]
WantedBy=default.target
UNIT_EOF
  }
  systemctl --user daemon-reload && systemctl --user enable --now memt-daemon && echo "ok: 守护已启（开机自启）"
else
  echo "skip: MEM_SKIP_UNIT=1"
fi

# ④ 自检环（fail-fast）
echo "== ④ 自检 =="
sleep 1
H=$(curl -s -m 3 "http://127.0.0.1:$PORT/health" || true)
if echo "$H" | grep -q '"ok": true'; then
  echo "ok: daemon health $(echo "$H" | head -c 120)"
else
  echo "WARN: daemon 未答（fail-soft 不阻安装——记忆面缺失不阻宿主回复）"
fi
python3 -c "import json; g=json.load(open('$MEM_HOME/config/daemon_forward.json')) if __import__('os').path.exists('$MEM_HOME/config/daemon_forward.json') else {}; print('gate:', g.get('enabled'), g.get('sessions'))" 2>/dev/null || echo "gate: 未配（转接层默认关=原路径）"

echo ""
echo "== ✅ 安装完成 =="
echo "家: $MEM_HOME/家（T0 账本）· state/ · shadow/ · tmp/"
echo "卸载: bash $HERE/deploy/uninstall.sh（T0 账本永不删）"
