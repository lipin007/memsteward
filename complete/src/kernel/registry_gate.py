import json
"""提取件 v1（2026-11-19 组件提取入册）
来源：src/bridge_cli.py 行 [(385, 417)]
状态：已接线（P1 单源化 2026-11-19，kernel 装配）。发现面走代码的家（家模式，2026-11-19 用户拍板仿 openclaw）。
"""
def registry_gate(ws):
    """入册门自动化（S2 同哲学：声明不算数，探针才算数）。

    发现面走代码的家（家模式，仿照 openclaw，2026-11-19 用户拍板）：
      plugins 扫 $MEMSTEWARD_HOME/plugins/*/openclaw.plugin.json（跳过 .bak）
      产品  扫 $MEMSTEWARD_HOME/products/* 顶层产物名(每产品一独立夹, 2026-11-19 定名)
    家默认 ~/.memsteward（MEMSTEWARD_HOME 可覆写）；登记账仍查 ws/memory/branches/registry.md。
    未登记的产物视为不存在（揪出即警示）；家面缺席＝可见跳过（note），不静默；无内容空壳不算产品(鬼影清除同哲学)。
    """
    import os

    home = os.environ.get("MEMSTEWARD_HOME") or os.path.expanduser("~/.memsteward")
    rp = os.path.join(ws, "memory", "branches", "registry.md")
    if not os.path.isfile(rp):
        return {"ok": True, "checked": 0, "unregistered": [], "note": "registry.md 不存在（跳过）"}
    with open(rp, encoding="utf-8") as f:
        text = f.read().lower()
    notes = []
    cands = []
    pdir = os.path.join(home, "plugins")
    if os.path.isdir(pdir):
        for x in sorted(os.listdir(pdir)):
            if ".bak" in x:
                continue
            pj = os.path.join(pdir, x, "openclaw.plugin.json")
            if os.path.isfile(pj):
                try:
                    with open(pj, encoding="utf-8") as f:
                        cands.append(json.load(f).get("id") or x)
                except Exception:
                    cands.append(x)
    else:
        notes.append("家 plugins 面缺席（跳过）: " + pdir)
    base = os.path.join(home, "products")
    if os.path.isdir(base):
        for x in sorted(os.listdir(base)):
            if os.path.isdir(os.path.join(base, x)):
                cands.append(x)
    else:
        notes.append("家 products 面缺席（跳过）: " + base)
    unreg = [c for c in cands if c.lower() not in text]
    out = {"ok": not unreg, "checked": len(cands), "unregistered": unreg}
    if notes:
        out["note"] = "; ".join(notes)
    return out


BRIDGE_PROTOCOL = 3  # 桥协议版本（TS↔Python 调用面契约；调用面语义变更即升位）
# v2 (2026-11-04): recall 默认带 min_liveness 量门（冷条目不注入≠删除）——旧调用方结果集变小，语义升位
# v3 (2026-11-12): 写入侧准入（五病#1）——deposit/observe/summarize-flush 可返回
#   rejected/quarantined；recall 默认合格面排除 admit=quarantine 条目（排除≠删除）

