# -*- coding: utf-8 -*-
"""pvs.gate.ledger —— 环3 过程级: 教训台账 (2026-11-02 波次31 交付A)。

治「边开发边忘记」: 每条教训 = 结构化六字段 + 一条可执行断言 (preflight 跑得到才算数)。
元教训 L01 本身也在台账里: 写下教训 ≠ 改掉行为 —— 没有固化命令模板/断言的教训不算入册。

字段:
  id           编号
  lesson       教训原文
  source       出处 (memory/2026-11-02.md / AGENTS.md 工程铁律 / 任务红线)
  trigger      触发场景 (什么时候该想起这条)
  check_item   行为检查项 (开工前问自己的那句话)
  assertion    可执行断言 {kind: auto|decl, fn: 检查函数名 | cmd_template}
  evidence     验证证据 (实锤: 谁在什么时候踩的)
  cmd_template 固化命令模板 (照做, 不靠记忆)
"""
from __future__ import annotations

LESSONS = [
    {
        "id": "L01",
        "lesson": "写下教训 ≠ 改掉行为 —— 工具类教训必须当场固化成命令模板/可执行断言, 否则必重犯",
        "source": "AGENTS.md 工程铁律1 元教训 (2026-09-20)",
        "trigger": "任何一条新教训入册 / 复盘冒出「下次注意」时",
        "check_item": "台账每条是否都带非空固化命令模板 + 接进 preflight 断言? preflight 跑不到的教训 = 没改掉",
        "assertion": {"kind": "auto", "fn": "check_ledger_integrity"},
        "evidence": "pkill -f 双杀实锤: 第 2 次就发生在刚写下这条教训的同一条消息里 (AGENTS.md 铁律1)",
        "cmd_template": "python3 -m pvs.gate preflight   # 全绿才算改掉; 无断言的教训禁止入册",
    },
    {
        "id": "L02",
        "lesson": "进程收尾一律按 pid / pgrep -x; 禁用 pkill -f / pgrep -f 匹配命令行",
        "source": "AGENTS.md 工程铁律1 (2026-09-20)",
        "trigger": "起/杀/查任何后台进程时",
        "check_item": "杀进程是否 kill $PID? 查进程是否 pgrep -x? 脚本里有没有 pkill -f?",
        "assertion": {"kind": "auto", "fn": "check_pid_discipline"},
        "evidence": "pkill -f \"godot --headless\" 与 pgrep -f \"main.gd\" 各自杀一次 (含自己命令行)",
        "cmd_template": "PID=$!; ...; kill $PID        # 查: pgrep -x <进程名>; 起后台当场记 $!",
    },
    {
        "id": "L03",
        "lesson": "验证必须 fail-fast: 关键校验用 && / || exit 1 串联, 禁止 ; 一路跑到底",
        "source": "AGENTS.md 工程铁律4 (2026-09-19 事故后立)",
        "trigger": "写任何校验命令链 (py_compile/回归/selftest/提交) 时",
        "check_item": "命令链里 py_compile/pytest 之后是不是 &&? 有没有 ; 串联关键校验?",
        "assertion": {"kind": "auto", "fn": "check_failfast_chains"},
        "evidence": "py_compile 失败后照跑完并提交了坏代码 (2026-09-19)",
        "cmd_template": "python3 -m py_compile foo.py && python3 -m arc_core selftest && git commit ...   # 全程 &&",
    },
    {
        "id": "L04",
        "lesson": "改机制前后做「同批对照」再下结论; 别拿旧文档数字当基线",
        "source": "AGENTS.md 工程铁律2 (2026-09-20)",
        "trigger": "任何机制/判据/默认参数变更的前后对比时",
        "check_item": "对照是不是同一批种子 git stash 前后跑出来的? 基线是现跑的还是文档抄的?",
        "assertion": {"kind": "decl", "cmd_template": "git stash push -- <files> && <同批种子运行> && git stash pop   # 前后同批"},
        "evidence": "一次「默认路径行为变了」误判, 真因是旧记录陈旧 (其间别的提交改过判据)",
        "cmd_template": "git stash push -- <改动文件> && <跑同批种子记录> && git stash pop && <再跑同批对比>",
    },
    {
        "id": "L05",
        "lesson": "动「新世界/新接口」: 先读源码 → 再离线体检 → 才改代码 (顺序固定)",
        "source": "AGENTS.md 工程铁律3 (2026-09-20)",
        "trigger": "接入任何不熟的模块/引擎/接口前",
        "check_item": "源码读了吗? 声明层体检 (分组极差/基准率/伪影) 做了吗? 还是直接上手改?",
        "assertion": {"kind": "decl", "cmd_template": "grep -n <接口名> <源码> | head; python3 <离线体检脚本>   # 读源码→体检→才改"},
        "evidence": "接 Godot 时自造 4 个「成功量」代理全失败, 而适配器本来就返回动作前后态; 朴素解码造出伪分离",
        "cmd_template": "① grep/read 源码 ② 离线声明层体检 ③ 才改代码   # 三步不许跳",
    },
    {
        "id": "L06",
        "lesson": "审计门禁拦下时: 复核 → 按门禁格式补「已复核的那一条」→ 正常提交 (不 SKIP)",
        "source": "AGENTS.md 工程铁律5 (2026-09-20)",
        "trigger": "提交被审计/门禁脚本拦下时",
        "check_item": "是补了已复核条目再交, 还是想 SKIP/绕过门禁?",
        "assertion": {"kind": "decl", "cmd_template": "python3 <门禁> --baseline '<commit>:<file>:<key>'   # 只补已复核那条"},
        "evidence": "门禁两次拦下; 正解=补 _audit/preflight_baseline.json 对应键 (含 list 型), 不做全量 --baseline",
        "cmd_template": "复核 → 补 _audit/preflight_baseline.json 单条 (格式 <commit>:<file>:<key>) → 正常提交",
    },
    {
        "id": "L07",
        "lesson": "远程仓库 = 橱窗: 推送标准是「该不该展示」; 发布门禁全过才推, 一门不过 = 不上",
        "source": "AGENTS.md 工程铁律6 (2026-10-13 拍板)",
        "trigger": "任何 git push / 上架 / 对外发布前",
        "check_item": "陈列清单=成品? 六门 (展品/敏感/专利/数字/形态/拍板) 都过了吗? 授权拿到了吗?",
        "assertion": {"kind": "decl", "cmd_template": "<六门逐项打勾后> git push   # 话术禁用「领先 N 提交」"},
        "evidence": "以「仓库领先 12 提交」催推被纠正; 工作台提交流不是展品 (2026-10-13 二次实锤)",
        "cmd_template": "列展品清单 → 六门审查 (含专利范围双核对) → 用户明示「上传/上架」→ squash 陈列提交 → push",
    },
    {
        "id": "L08",
        "lesson": "先落盘后交账: 报单必须含 stat -c%s 实测字节 (+sha256 现场重算), 与实盘逐字节对账",
        "source": "memory/2026-11-02.md (交付报单教训)",
        "trigger": "任何交付/报单/汇报产物清单时",
        "check_item": "每个交付物的字节数是 stat -c%s 现场量的, 还是估的/抄旧文档的?",
        "assertion": {"kind": "auto", "fn": "check_report_stat_bytes"},
        "evidence": "交付报单必须「报单与实盘逐字节对账」(stat＋sha256 现场重算＋层数逐层核对) 的实锤要求",
        "cmd_template": "stat -c%s <files> && sha256sum <files>   # 报单格式: `路径` = N B",
    },
    {
        "id": "L09",
        "lesson": "「跑批吃钉死快照」必须用模块 __file__ 实证, 不能信 sys.path 写法",
        "source": "memory/2026-11-02.md (教训入册)",
        "trigger": "批量脚本/长跑脚本钉死输入快照、拼模块路径时",
        "check_item": "快照路径是不是从 __file__ 锚定导出的? 有没有裸 sys.path.insert 碰运气?",
        "assertion": {"kind": "auto", "fn": "check_snapshot_pin"},
        "evidence": "教训入册原话: 跑批吃钉死快照必须用模块 __file__ 实证, 不能信 sys.path 写法",
        "cmd_template": "HERE = os.path.dirname(os.path.abspath(__file__))   # 一切快照路径从 HERE 导出",
    },
    {
        "id": "L10",
        "lesson": "下判语前先确认量具边界 (同型错误已第 4 次): 每个数先问「采集边界是什么」",
        "source": "memory/2026-11-02.md (元教训第 4 次印证)",
        "trigger": "对任何指标/计数/曲线下结论前",
        "check_item": "这个数是全量还是单点样? 计数点挂在「选了它」还是执行段? t= 是步号还是秒?",
        "assertion": {"kind": "decl", "cmd_template": "grep -n '<计数点位置>' <埋点源码>   # 量具边界先实证再下判"},
        "evidence": "acct 陈旧单点样 / 计数点挂执行段 / t= 步号误读 / 诊断窗当动作计数, 四次同型",
        "cmd_template": "先写清「量具+采集边界+口径」三行 → 再下判语; 边界不清 = 只报事实不报结论",
    },
    {
        "id": "L11",
        "lesson": "归因污染: 一次只动一个变量; 赢数动了要分得清是谁动的",
        "source": "memory/2026-11-02.md (收敛铁律旁证)",
        "trigger": "一次实验/改动要验证效果时",
        "check_item": "这次改动和上次之间隔了几个变量? 能归因到单一改动吗?",
        "assertion": {"kind": "decl", "cmd_template": "git diff --stat   # 一次提交只许含一个可归因变量"},
        "evidence": "归因污染: 赢数动了分不清谁动的, 收敛铁律下两边都只能算半个证明",
        "cmd_template": "单变量提交 → 同批对照 (L04) → 再叠加下一个变量",
    },
    {
        "id": "L12",
        "lesson": "禁止 2 个及以上 20B 级大模型同时计算（并发推理会卡死机器）；后台待命/常驻不算，3B/4B 小模型与 embedding 不在此限（管并发计算，不是管进程数）",
        "source": "波次31 任务红线 (2026-11-02 用户严令)",
        "trigger": "任何要起 llama-server / ollama / vllm 之类进程前",
        "check_item": "现在有几台 20B 级大模型在并发计算？（待命不算；3B/4B 与 embedding 不计）",
        "assertion": {"kind": "auto", "fn": "check_llm_process_count"},
        "evidence": "27B 被杀 + 用户严令（当时口径）；,
        "cmd_template": "pgrep -x llama-server   # ≤1 个非 embedding 才放行; 纯建设期要求 0",
    },
    {
        "id": "L13",
        "lesson": "googleapis 死 IP: 本机解析 *.googleapis.com 混死 IP, 上传/联网必须走 socket.getaddrinfo 钉法 (rootless hosts 钉法, TLS SNI/证书不变)",
        "source": "memory/2026-11-03.md B2 教训1 + kaggle_kernel_shot2/_g02_weight_channel_report.md (2026-11-02 23:13 实锤)",
        "trigger": "任何 kaggle CLI 上传 / 联网访问 googleapis 域前",
        "check_item": "上传脚本走了 upload_pinned.py 钉法吗? 存活 IP 是 curl --resolve 实测过的吗? 裸直连 = 必卡 SYN-SENT",
        "assertion": {"kind": "auto", "fn": "check_dns_pin"},
        "evidence": "首试 0B: SYN-SENT 卡死 172.217.117.4 (www.googleapis.com 死 IP, GFW); 钉法后 7.53MB/s 续传成功 (16.46GB)",
        "cmd_template": "curl --resolve www.googleapis.com:443:<live-ip> -sI https://www.googleapis.com  # 先验存活 IP → python3 _upload_qwen38_27b_ops/upload_pinned.py <kaggle 参数>",
    },
]


def get_lesson(lid: str):
    for ls in LESSONS:
        if ls["id"] == lid:
            return ls
    return None
