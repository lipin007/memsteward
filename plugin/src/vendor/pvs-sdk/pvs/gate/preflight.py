# -*- coding: utf-8 -*-
"""pvs.gate.preflight —— 开工前断言检查器 (2026-11-02 波次31 交付A)。

把台账每条教训转成可执行断言, 开工前跑一遍:

    python3 -m pvs.gate preflight              # 全部断言
    python3 -m pvs.gate preflight --report <报单.md>   # 带报单对账 (L08)
    python3 -m pvs.gate preflight --json       # 机器可读 (报告集成)
    python3 -m pvs.gate preflight --strict     # DECL(人工确认项) 未确认也算 FAIL

断言类型:
  auto  = 本机自动扫描 (进程/脚本/快照锚定/台账完整性/报单对账)
  decl  = 需人工确认的行为项; 输出确认口令 + 固化命令模板 (--ack L04,L05 显式确认)

退出码: 0 = 全过; 1 = 有 FAIL。preflight 自己也守 L03: 全程 && 语义, fail-fast。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(HERE))          # arc-agi-2 (L09: __file__ 锚定)
WS_ROOT = os.path.dirname(_ROOT)

from .ledger import LESSONS                                # noqa: E402

# 扫描范围: 本仓 py/sh (排除冻结区大件目录与本模块自身无须排除)
_SCAN_EXCL_DIR = {"__pycache__", ".git", "node_modules",
                  "submission_run_v1_out", "kaggle_kernel_shot1", "kaggle_kernel_shot2",
                  "site-packages", "openclaw-src", ".venv-nle", ".trash_ai-research_cleared_20260912"}  # 2026-11-20 范围修: 第三方(venv/openclaw 上游)/实验快照/垃圾箱不属治理扫描面
_MAX_SCAN_FILES = 4000

_OK, _FAIL, _DECL = "PASS", "FAIL", "DECL"

_BASELINE_FILE = os.path.join(HERE, "preflight_baseline.json")
# L09 口径: 教训入册日之后新增/改动的脚本必须 __file__ 锚定;
# 入册前历史散件不计 (改到哪修到哪), 基线文件仍可显式点名复核。
_L09_EPOCH = 1793548800.0        # 2026-11-02 00:00 +08:00 教训入册日


def _load_baseline(lesson_id):
    """已复核历史基线 (L06 精神: 只保护逐条复核过的旧账, 新命中必须真修)。"""
    try:
        data = json.load(open(_BASELINE_FILE))
        return set(data.get(lesson_id, []))
    except Exception:
        return set()


def _iter_code_files():
    """L09 纪律: 从 __file__ 锚定的 _ROOT 走目录, 不猜 cwd。"""
    n = 0
    for dirpath, dirnames, filenames in os.walk(_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SCAN_EXCL_DIR]
        for fn in filenames:
            if not fn.endswith((".py", ".sh")):
                continue
            # E2 自扫排除: 检查器家族 (gate/process) 自身的说明文字含
            # "pkill -f"/"; 串联"等 pattern 字面量, 外部根扫描时会误伤自己。
            if fn in ("preflight.py", "ledger.py", "boot.py") and \
               os.path.basename(dirpath) in ("gate", "process"):
                continue
            yield os.path.join(dirpath, fn)
            n += 1
            if n >= _MAX_SCAN_FILES:
                return


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


# ─────────────────────────── auto 断言实现 ───────────────────────────

def check_ledger_integrity(ctx):
    """L01: 台账每条必须有教训原文/触发场景/行为检查项/验证证据/固化命令模板 + 断言。"""
    bad = []
    for ls in LESSONS:
        for field in ("lesson", "trigger", "check_item", "evidence", "cmd_template"):
            if not str(ls.get(field, "")).strip():
                bad.append(f"{ls['id']} 缺 {field}")
        a = ls.get("assertion") or {}
        if a.get("kind") not in ("auto", "decl"):
            bad.append(f"{ls['id']} 断言类型非法")
        if a.get("kind") == "auto" and a.get("fn") not in globals():
            bad.append(f"{ls['id']} 断言函数 {a.get('fn')} 不存在")
    if bad:
        return _FAIL, "台账不完整: " + "; ".join(bad)
    return _OK, f"{len(LESSONS)} 条教训六字段齐全, 断言全部注册"


def check_pid_discipline(ctx):
    """L02: 仓内脚本禁用 pkill -f / pgrep -f (匹配自己命令行的自杀实锤)。"""
    hits = []
    for path in _iter_code_files():
        if os.path.abspath(path).startswith(os.path.abspath(HERE)):
            continue                                   # 本检查器自身引用 pattern 不算
        text = _read(path)
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"\bpkill\s+-f\b|\bpgrep\s+-f\b", line):
                hits.append(f"{os.path.relpath(path, _ROOT)}:{i}")
    if hits:
        return _FAIL, "发现 pkill -f/pgrep -f: " + ", ".join(hits[:8])
    return _OK, "仓内 py/sh 零 pkill -f / pgrep -f (进程一律 pid/`pgrep -x`)"


def check_failfast_chains(ctx):
    """L03: 关键校验 (py_compile/pytest/回归) 不得用 `;` 串联。"""
    pat = re.compile(r"(py_compile|pytest|run_full_regression|selftest)[^\n;&|]{0,120};(?! ?(?:then|do)\b)")  # 2026-11-20 精化: 排除 if/循环控制结构的分号(真违例=check; check 串联)
    hits = []
    for path in _iter_code_files():
        if os.path.abspath(path).startswith(os.path.abspath(HERE)):
            continue                                   # 检查器自身含 pattern 字面量, 不自扫
        text = _read(path)
        for i, line in enumerate(text.splitlines(), 1):
            if pat.search(line):
                hits.append(f"{os.path.relpath(path, _ROOT)}:{i}")
    # 已复核基线 (L06 精神: 复核→补已复核那条→正常放行; 新增命中不受基线保护)
    base = _load_baseline("L03")
    new_hits = [h for h in hits if h.split(":")[0] not in base]
    if new_hits:
        return _FAIL, "关键校验疑似 `;` 串联: " + ", ".join(new_hits[:8])
    n_base = len(hits) - len(new_hits)
    return _OK, (f"未发现新增 `;` 串联 (fail-fast 链)"
                 + (f"; 历史基线已复核 {n_base} 条" if n_base else ""))


def check_snapshot_pin(ctx):
    """L09: 快照/数据路径必须从 __file__ 锚定导出; 禁裸 sys.path.insert 猜路径吃钉死快照。"""
    suspect = []
    for path in _iter_code_files():
        rel = os.path.relpath(path, _ROOT)
        if rel.startswith("arc_core" + os.sep):        # 包内 __init__ 常规写法, 另有规范
            continue
        text = _read(path)
        if not text:
            continue
        if re.search(r"\bsys\.path\.insert\(", text) and not ("__file__" in text and "abspath" in text):
            # 教训入册 (2026-11-02) 后新增/改动的脚本才算违规; 入册前散件不计
            if os.path.getmtime(path) < _L09_EPOCH:
                continue
            suspect.append(rel)
    base = _load_baseline("L09")
    new_hits = [s for s in suspect if s not in base]
    if new_hits:
        return _FAIL, "裸 sys.path 且无 __file__ 锚定 (入册后新件): " + ", ".join(new_hits[:8])
    return _OK, (f"入册 (2026-11-02) 后新/改脚本均 __file__ 锚定; "
                 f"历史散件基线 {len(base)} 个已逐个复核入册 (改到哪修到哪)")


def check_llm_process_count(ctx):
    """L12: 20B 级大模型并发计算 <=1 (管「同时计算」的卡死风险;
    后台待命/常驻不算; 3B/4B 小模型与 embedding 不计)。判据=并发计算中的大模型数 >=2 才 FAIL。"""
    try:
        out = subprocess.run(["pgrep", "-x", "llama-server"], capture_output=True,
                             text=True, timeout=5)
        pids = [p for p in out.stdout.split() if p.strip()]
    except Exception:
        pids = []
    active_large, standby_large = [], []
    for pid in pids:
        cmdline = _read("/proc/%s/cmdline" % pid).replace(chr(0), " ")
        if "--embedding" in cmdline:
            continue
        size = _model_size_b(cmdline)
        if size is not None and size < 20:
            continue                      # 3B/4B 等小/中模型不计(L12 豁免)
        (active_large if _is_computing(pid) else standby_large).append(pid)
    if len(active_large) >= 2:
        return _FAIL, ("20B 级大模型并发计算 %d 个 (pid: %s) -- 同时计算卡死风险 (L12; 待命不计)"
                       % (len(active_large), active_large))
    if active_large or standby_large:
        return _OK, ("20B 级大模型: 计算中 %d, 待命 %d (并发计算 <=1 合规; L12 管并发计算不是管进程数)"
                     % (len(active_large), len(standby_large)))
    return _OK, "无 20B 级大模型在跑 (L12 合规)"


def _model_size_b(cmdline):
    """从模型文件名提取参数规模(B); 提不出=None(按大模型保守计)。"""
    for tok in cmdline.split():
        if ".gguf" in tok:
            m = re.search(r"[-_.](\d+(?:\.\d+)?)[bB][-_.]", tok)
            if m:
                return float(m.group(1))
    return None


def _is_computing(pid, window=0.4):
    """短窗 CPU 占用判定: 计算态 >20% 算在算, 否则待命 (L12 并发计算口径)。"""
    import time
    try:
        def ticks():
            return sum(int(x) for x in _read("/proc/%s/stat" % pid).rsplit(")", 1)[1].split()[11:13])
        t0 = ticks()
        time.sleep(window)
        t1 = ticks()
        clk = os.sysconf("SC_CLK_TCK")
        return (t1 - t0) / float(clk * window) > 0.20
    except Exception:
        return False


def check_dns_pin(ctx):
    """L13: googleapis 死 IP 防线 —— kaggle 上传必须走 socket.getaddrinfo 钉法。
    勘误 E1 (整合施工方案_v1 §5): 适用性门控 —— 无 kaggle 上传活动的工作区
    =PASS(不适用); 有上传活动则必须走钉法且钉法脚本在位 (防工作区耦合误报)。"""
    bad, pin_refs, any_upload = [], 0, False
    for path in _iter_code_files():
        rel = os.path.relpath(path, _ROOT)
        if os.path.abspath(path).startswith(os.path.abspath(HERE)):
            continue                                   # 检查器自身不自扫
        text = _read(path)
        if re.search(r"\bkaggle\s+(datasets|models)\s+(create|version|upload|push)\b", text):
            any_upload = True
            if "getaddrinfo" in text or "upload_pinned" in text:
                pin_refs += 1
            else:
                bad.append(rel)
    if bad:
        return _FAIL, "kaggle 上传未走钉法: " + ", ".join(bad[:6])
    if not any_upload:
        return _OK, "本工作区无 kaggle 上传活动 (L13 不适用); 钉法机制保留在台账"
    pins = [p for p in _iter_code_files() if os.path.basename(p) == "upload_pinned.py"]
    good_pins = [p for p in pins if "getaddrinfo" in _read(p)]
    if pin_refs and not good_pins:
        return _FAIL, "上传引用钉法但 upload_pinned.py 缺失/被改坏"
    return _OK, f"kaggle 上传 {pin_refs} 处均走钉法; 合格钉法脚本 {len(good_pins)} 个"


def check_report_stat_bytes(ctx):
    """L08: 报单与实盘逐字节对账 —— 报单里 `路径` = N B 声明逐个 stat -c%s 复核。"""
    report = ctx.get("report_path")
    if not report:
        return _DECL, "未带 --report <报单.md>; 交账前请用 --report 复核 (stat -c%s 实测字节)"
    text = _read(report)
    if not text:
        return _FAIL, f"报单不可读: {report}"
    decls = re.findall(r"`([^`]+)`\s*=\s*([\d,]+)\s*B", text)
    if not decls:
        return _FAIL, "报单无 `路径` = N B 声明 (L08: 必须含 stat -c%s 实测字节)"
    bad = []
    for rel, size in decls:
        target = rel if os.path.isabs(rel) else os.path.join(_ROOT, rel)
        if not os.path.isfile(target):
            bad.append(f"{rel} 不存在")
            continue
        actual = os.path.getsize(target)
        if actual != int(size.replace(",", "")):
            bad.append(f"{rel} 报 {size} 实 {actual}")
    if bad:
        return _FAIL, "报单对账不符: " + "; ".join(bad[:6])
    return _OK, f"报单 {len(decls)} 项 stat -c%s 全部对上"


# ─────────────────────────── 运行器 ───────────────────────────

def run_preflight(report_path=None, ack=None, strict=False, root=None):
    """跑全部断言, 返回 (rows, ok)。rows: [{id, lesson, kind, status, detail, cmd}]。
    root= 可选: 对任意工作区跑门禁（产品化参数, 供 boot/外部工作区调用）。
    """
    global _ROOT, WS_ROOT
    _saved = (_ROOT, WS_ROOT)
    if root:
        _ROOT = os.path.abspath(root)
        WS_ROOT = os.path.dirname(_ROOT)
    try:
        return _run_preflight_inner(report_path=report_path, ack=ack, strict=strict)
    finally:
        _ROOT, WS_ROOT = _saved


def _run_preflight_inner(report_path=None, ack=None, strict=False):
    ack = set(ack or [])
    ctx = {"report_path": report_path}
    rows = []
    ok = True
    for ls in LESSONS:
        a = ls.get("assertion") or {}
        kind = a.get("kind")
        if kind == "auto":
            fn = globals().get(a.get("fn", ""))
            if fn is None:
                status, detail = _FAIL, f"断言函数缺失: {a.get('fn')}"
            else:
                try:
                    status, detail = fn(ctx)
                except Exception as e:                    # 断言自身炸了 = FAIL, 不静默
                    status, detail = _FAIL, f"断言异常: {e}"
        else:
            if ls["id"] in ack:
                status, detail = _OK, "已人工确认 (--ack)"
            else:
                status, detail = _DECL, "待人工确认: " + ls["check_item"]
        if status == _FAIL or (strict and status == _DECL):
            ok = False
        rows.append({"id": ls["id"], "lesson": ls["lesson"][:40], "kind": kind,
                     "status": status, "detail": detail,
                     "cmd": ls.get("cmd_template", "")})
    return rows, ok


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m pvs.gate preflight",
                                 description="教训台账 → 可执行断言, 开工前跑一遍")
    ap.add_argument("--report", default=None, help="报单 md 路径 (L08 逐字节对账)")
    ap.add_argument("--ack", default="", help="逗号分隔人工确认项, 如 L04,L05")
    ap.add_argument("--strict", action="store_true", help="DECL 未确认也算 FAIL")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args(argv)

    ack = [x.strip() for x in args.ack.split(",") if x.strip()]
    rows, ok = run_preflight(report_path=args.report, ack=ack, strict=args.strict)

    if args.json:
        print(json.dumps({"ok": ok, "rows": rows}, ensure_ascii=False, indent=1))
        return 0 if ok else 1

    print("=== preflight（教训台账 → 可执行断言） ===")
    for r in rows:
        mark = {_OK: "[ OK ]", _FAIL: "[FAIL]", _DECL: "[DECL]"}[r["status"]]
        print(f"{mark} {r['id']} {r['lesson']}")
        print(f"        {r['detail']}")
        if r["status"] != _OK and r["cmd"]:
            print(f"        模板: {r['cmd']}")
    n_fail = sum(1 for r in rows if r["status"] == _FAIL)
    n_decl = sum(1 for r in rows if r["status"] == _DECL)
    print(f"--- 结论: {len(rows)} 项, FAIL {n_fail}, DECL {n_decl} → "
          f"{'开工放行' if ok else '先修 FAIL/补确认'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
