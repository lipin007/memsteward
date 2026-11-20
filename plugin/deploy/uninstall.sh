#!/usr/bin/env bash
# MemGate/记忆体 · 卸载件 v1（2026-11-10）
# 铁则：T0 账本（~/.memsteward/landing/）永不删除——卸载=移除程序与接线，记忆资产是主人的。
# 幂等：重复运行无害。fail-soft：每步独立，失败不中断后续。
# 测试口：MEMGATE_CONFIG=<path> 覆盖配置文件；MEMGATE_SKIP_SYSTEMD=1 跳过守护步骤；
#         MEMGATE_SKIP_PLUGIN_UNINSTALL=1 跳过 openclaw plugins uninstall（隔离测试用，防误伤现网）。
set -uo pipefail

CFG="${MEMGATE_CONFIG:-$HOME/.openclaw/openclaw.json}"
GATE="$HOME/.openclaw/（开发仓路径）/商用产品/MemGate/config/daemon_forward.json"

echo "== ① 停守护（memt-body.service，systemd 瞬态单元）=="
if [ "${MEMGATE_SKIP_SYSTEMD:-0}" = "1" ]; then
  echo "skip: 测试模式（MEMGATE_SKIP_SYSTEMD=1）"
else
  systemctl --user stop memt-body.service 2>/dev/null && echo "ok: 守护已停" || echo "skip: 守护未在跑"
  systemctl --user reset-failed memt-body.service 2>/dev/null || true
fi

echo "== ② 摘插件接线（load.paths 的 MemGate 项 ＋ plugins.entries.memgate ＋ 双槽绑定）=="
python3 - "$CFG" <<'PYEOF'
import json, os, sys
p = sys.argv[1]
if not os.path.exists(p):
    print(f"skip: 配置不在 {p}"); raise SystemExit(0)
d = json.load(open(p))
changed = []
paths = (d.get("plugins", {}).get("load", {}) or {}).get("paths", []) or []
keep = [x for x in paths if "MemGate" not in str(x)]
if len(keep) != len(paths):
    d["plugins"]["load"]["paths"] = keep; changed.append(f"load.paths -{len(paths)-len(keep)}")
if "memgate" in (d.get("plugins", {}).get("entries", {}) or {}):
    del d["plugins"]["entries"]["memgate"]; changed.append("entries.memgate")
for slot in ("memory", "contextEngine"):
    if d.get(slot) == "memgate":
        d[slot] = None; changed.append(f"{slot} 槽解绑")
if changed:
    json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
    print("ok: 已摘 →", ", ".join(changed))
else:
    print("skip: 无插件接线可摘")
PYEOF

echo "== ③ 卸载已安装包（openclaw plugins install 形态才有）=="
if [ "${MEMGATE_SKIP_PLUGIN_UNINSTALL:-0}" = "1" ]; then
  echo "skip: 测试模式（MEMGATE_SKIP_PLUGIN_UNINSTALL=1）"
elif command -v openclaw >/dev/null 2>&1; then
  openclaw plugins uninstall memgate 2>/dev/null && echo "ok: 包已卸" || echo "skip: 无已安装包（链装模式无需此步）"
fi

echo "== ④ 转接层 gate 收闸（文件保留可回滚）=="
if [ -f "$GATE" ]; then
  python3 - "$GATE" <<'PYEOF'
import json, sys
g = json.load(open(sys.argv[1]))
g["enabled"] = False; g["toolfaceHook"] = False
json.dump(g, open(sys.argv[1], "w"), ensure_ascii=False, indent=2)
print("ok: gate 已关（enabled=false, toolfaceHook=false）")
PYEOF
else
  echo "skip: gate 文件不在"
fi

echo ""
echo "== ✅ 卸载完成 =="
echo "★ 保留（永不删）：T0 账本 ~/.memsteward/landing/ —— 记忆资产属主人，卸载不删记忆"
echo "★ 保留：工作区源码/文档（生产树不动）"
echo "重装：openclaw plugins install <包>/dist/memgate-*.tgz，或 plugins.load.paths 指回工作区后重启网关"
