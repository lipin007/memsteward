import sys
# 装配位自适应(2026-11-19 P1): kernel/ 位回退到 src/ 以保持 HERE=产品 src 根语义
HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
if __import__("os").path.basename(HERE) == "kernel":
    HERE = __import__("os").path.dirname(HERE)

BRIDGE_PROTOCOL = 3  # 桥协议版本(TS↔Python 调用面契约; 单源收编自 bridge_cli 2026-11-19 P1)

def _bootstrap(ws):
    """随包 vendor 优先=产品自含(单源收编自 bridge_cli)"""
    for name in ("calldecacy-sdk", "pvs-sdk"):
        p = os.path.join(HERE, "vendor", name)
        if not os.path.isdir(p):
            p = os.path.join(ws, "中间件", "组件总文件夹", name)
        if p not in sys.path:
            sys.path.insert(0, p)

import os
import json
import time
import hashlib
"""提取件 v1（2026-11-19 组件提取入册）
来源：src/bridge_cli.py 行 [(426, 530)]
状态：未接线提取稿。接线前按本夹 README 的参数化清单补齐。
"""
def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _version(ws, write=False, manifest_path=None, config_path=None, model_path=None):
    """版本管理与绑定：实测值 ↔ VERSIONS.json 清单逐项核对（声明不算数，重算才算数）.

    write=True → 以现场实测值落盘绑定清单（原子写，幂等）；
    默认       → 清单↔实测核对，bound/mismatches 如实报。
    """
    root = os.path.abspath(os.path.join(HERE, ".."))
    mpath = manifest_path or os.path.join(root, "VERSIONS.json")
    cfg_path = (config_path or os.environ.get("OPENCLAW_CONFIG")
                or os.path.expanduser("~/.openclaw/openclaw.json"))

    # ── 现场实测值 ──
    live = {"bridgeProtocol": BRIDGE_PROTOCOL}
    try:
        with open(os.path.join(root, "package.json")) as f:
            live["version"] = json.load(f).get("version")
    except (OSError, ValueError):
        live["version"] = None
    _bootstrap(ws)
    try:
        import calldecay  # noqa: E402

        live["sdk"] = getattr(calldecay, "__version__", None)
    except Exception:  # noqa: BLE001 —— sdk 不可读如实报 None，不吞后谎报
        live["sdk"] = None
    try:
        import calldecay.landing as _land  # noqa: E402

        live["levers"] = {"decayFactor": getattr(_land, "DECAY_FACTOR", None),
                          "minLiveness": getattr(_land, "MIN_LIVENESS", None)}
    except Exception:  # noqa: BLE001 —— 杠杆常量随包缺如实报 None
        live["levers"] = None
    cfg = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
        except ValueError:
            cfg = {}
    slots = (cfg.get("plugins") or {}).get("slots") or {}
    search = (cfg.get("memory") or {}).get("search") or {}
    model = model_path or (search.get("local") or {}).get("modelPath")

    if write:
        emb = {}
        if model:
            m = os.path.expanduser(model)
            emb = {"modelPath": m,
                   "sha256": _sha256(m) if os.path.exists(m) else None}
        manifest = {
            "product": "MemGate",
            "component": "memgate",
            "version": live["version"],
            "sdk": live["sdk"],
            "bridgeProtocol": BRIDGE_PROTOCOL,
            "levers": live.get("levers"),
            "embedding": emb,
            "configBinding": {"memorySlot": slots.get("memory"),
                              "contextEngineSlot": slots.get("contextEngine")},
            "assembledAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        tmp = mpath + ".tmp"
        with open(tmp, "w") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        os.replace(tmp, mpath)  # L08：原子写
        return {"written": manifest, "path": mpath}

    mismatches = []
    manifest = None
    if os.path.exists(mpath):
        try:
            with open(mpath) as f:
                manifest = json.load(f)
        except ValueError:
            mismatches.append("manifest: 非法 JSON")
    else:
        mismatches.append("manifest 缺失（跑 --write 落盘）")
    if manifest:
        for key in ("version", "sdk", "bridgeProtocol", "levers"):
            if manifest.get(key) != live.get(key):
                mismatches.append(
                    f"{key}: 清单={manifest.get(key)!r} 实测={live.get(key)!r}")
        emb = manifest.get("embedding") or {}
        mp = emb.get("modelPath")
        if mp:
            if not os.path.exists(mp):
                mismatches.append(f"embedding: 模型文件缺失 {mp}")
            elif emb.get("sha256") != _sha256(mp):
                mismatches.append("embedding: 模型 sha256 漂移（清单≠现场重算）")
        cb = manifest.get("configBinding") or {}
        for key, live_v in (("memorySlot", slots.get("memory")),
                            ("contextEngineSlot", slots.get("contextEngine"))):
            if cb.get(key) != live_v:
                mismatches.append(
                    f"{key}: 清单={cb.get(key)!r} 实测={live_v!r}")
    return {"manifest": manifest, "live": live,
            "bound": not mismatches, "mismatches": mismatches}

