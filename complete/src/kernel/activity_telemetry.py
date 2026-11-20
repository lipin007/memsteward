import os
import json
import time

_HOME = os.environ.get("CALLDECACY_HOME") or os.path.expanduser("~/.memsteward/landing")  # 单源收编 2026-11-19
"""提取件 v1（2026-11-19 组件提取入册）
来源：src/bridge_cli.py 行 [(91, 102), (603, 630)]
状态：未接线提取稿。接线前按本夹 README 的参数化清单补齐。
"""
def _telemetry(landing, kind, cur):
    """good 族观测事件旁路账（JSONL，与账本同目录；观测失败 fail-soft 不阻业务）。"""
    try:
        base = (os.path.dirname(os.path.expanduser(landing)) if landing
                else _HOME)
        os.makedirs(base, exist_ok=True)
        with open(os.path.join(base, "telemetry.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "kind": kind, "cur": str(cur)[:80]},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass

def _bump_activity(landing=None, sub=None, **kv):
    """活动计数埋点（2026-11-09 面板）：逐子命令计数+末次时刻，kv 累加顶层键。
    fail-soft：埋点永不撑断工具调用。
    落点锚定**账本同目录**（2026-11-12 修：旧锚 $HOME——桥侧 HOME=fakehome 时
    埋点散落假家/静默丢，工具路召回计数缺口即此病）。"""
    try:
        base = (os.path.dirname(os.path.expanduser(landing)) if landing
                else _HOME)
        os.makedirs(base, exist_ok=True)
        p = os.path.join(base, "activity.json")
        d = {}
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            pass
        if sub is not None:
            s = d.setdefault("subs", {}).setdefault(str(sub), {"n": 0})
            s["n"] = int(s.get("n", 0)) + 1
            s["last"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        for k, v in kv.items():
            d[k] = int(d.get(k, 0)) + int(v)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception:
        pass

