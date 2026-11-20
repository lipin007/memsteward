# -*- coding: utf-8 -*-
"""CallDecay 落点件（Memory Landing）—— 记忆的"生死层"（整合施工方案_v1.md A 段）

治 CallDecay 的病：save() 从未被调用、记忆只活进程里（2dc448db 会话裁定）。
"记忆落点 vs CallDecay"之争的合成（A3 分工铁律）：
  - 落点层管**生死**：硬落盘（原子写 tmp+rename）、可寻址（sha1 id）、可回放（replay）
  - liveness 只管**召回排序**：旧的排后、被召回即保活——条目永不因衰减删除
  - provenance 盖章：每次 deposit/merge 带来源与时间戳
移植母本：arc-agi-2/arc_core/memory/rule_memory.py（同构合并 sha1＋Jaccard≥0.9）。
许可：工具层 Apache-2.0（无认知内核专利）——归层待用户确认（方案 §4 红线）。
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional
import unicodedata

MERGE_SIM = 0.9        # 同构合并阈值（Jaccard，与 rule_memory 同）
RECALL_GATE = 0.3      # 签名门控召回下限
DECAY_FACTOR = 0.9     # 每拍衰减系数（2026-11-04 17:1x 拍板调档 0.95→0.9：换「越用越省」绝对递减，敏感性 0.9/步 490→484 实证）
MIN_LIVENESS = 0.03    # 冷条目注入下限（「越用越省」量门；0.9^n≤0.03 ⇒ 约 34 个节拍未被召回即转冷；阈值扫描膝点）
# ★ 补丁①量门放行（2026-11-12 落地）：decision 拍板层免量门——全判终判实锤
#   9/9 低频关键拍板（liveness=0.01/hits=1）被 0.03 量门流放在召回面外
#   （experiments/对照臂_20261112/report_v2.md 失层①；full_verdict.json 翻案同批）。
#   summary 照旧受量门＋暖空捞冷 rescue；不注≠删语义两层同轨不变。
TICK_SECONDS = 3600.0  # 时间拍：闲置 1 小时＝1 拍（闲账也老化——补 2026-11-04 发现的空档）
AUTO_COMPACT_AT = 2000 # 冷层自动合账阈值（条数；触发后按保守三口径搬冷旧条目入归档）
DEFAULT_PATH = os.path.expanduser("~/.memsteward/landing/landing.json")

# ── shrink 快照保留策略（2026-11-08 混合保留拍板）─────────────────────────
# 场景: _write_now 的缩水护栏每次收缩留一份全量快照 landing.json.shrink-<ts>
# 当"落地写史"（历史不删），曾 25 小时积 910 份/1.94GB 且无上限。
# 口径: 原目录保留「最新 SHRINK_KEEP_COUNT 份 且 mtime ≤ SHRINK_KEEP_DAYS 天」
# 的现场缓冲；更旧快照 gzip 移入 <账本目录>/archive/<名>.gz——解压字节数
# 校验通过才摘原件（移动语义，永不 rm），全量历史随时可查。
# 可调环境变量: CALLDECAY_SHRINK_KEEP_COUNT (默认 20)
#              CALLDECAY_SHRINK_KEEP_DAYS  (默认 7)
#              CALLDECAY_SHRINK_SWEEP_MAX_PER_CALL (默认 10，写路径持锁单次上限)
SHRINK_KEEP_COUNT = int(os.environ.get("CALLDECAY_SHRINK_KEEP_COUNT", "20"))
SHRINK_KEEP_DAYS = float(os.environ.get("CALLDECAY_SHRINK_KEEP_DAYS", "7"))
SHRINK_SWEEP_MAX_PER_CALL = int(
    os.environ.get("CALLDECAY_SHRINK_SWEEP_MAX_PER_CALL", "10"))
SHRINK_ARCHIVE_SUBDIR = "archive"

# ── 召回热路径优化（2026-11-12 对照臂实测捎带发现）──────────────────────
# 实测（对照臂_20261112/out.json，12,006 条账本）：recall() 逐题 0.2676s 中
# 打分面只占 ~11%（转录类在 _entry_class 已拦、未进 bigram 打分）；大头是
# ①逐题 _reload_disk 全量重读 12MB≈82ms ②逐题 save 全量重写≈140ms
# ③逐题重算 eligible 词面≈23ms。三层治理，打分语义逐字不动：
#   - 词面缓存：cls+召回词面 bigram 集按 eid 缓存（内容变更即失效）
#   - stat 跳读：同锁下主文件 (dev,ino,size,mtime_ns) 未变＝其间无写入，
#     不重解析（一切写入持本锁）
#   - 保活提升日志：<账本>.liveness 追加日志（绝对值·只增·epoch 校验，
#     append+fsync≈0.44ms）——「被召回即保活」值即持久不变；全量写时并回
#     主文件清日志；主文件被整体换新（复制覆盖/崩溃残卷）旧保活随旧内容
#     作废（与旧语义一致）。日志超 MERGE_AT 行自动全量并回，有界。
# 验收：召回优化_20261112/out.json（78 题逐题全同＋提速倍数）。
LIVENESS_JOURNAL_SUFFIX = ".liveness"
LIVENESS_JOURNAL_MERGE_AT = 1024


def _gz_payload_bytes(path: str) -> int:
    """gzip 归档解压后的字节数（归档完整性校验用）。"""
    import gzip
    n = 0
    with gzip.open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            n += len(b)
    return n


def sweep_shrink_snapshots(ledger_path: str,
                           max_files: Optional[int] = None) -> Dict[str, int]:
    """shrink 快照保留清扫（2026-11-08 混合保留）：过保留门的快照 gzip 移入
    archive/，永不 rm。max_files=None 全量清扫（手动档）；写路径传
    SHRINK_SWEEP_MAX_PER_CALL 保持锁有界。返回 {kept, archived, pending, skipped}；
    校验不过/IO 失败一律留原件待下轮，绝不丢写史。"""
    import gzip
    import shutil
    d = os.path.dirname(ledger_path) or "."
    if not os.path.isdir(d):
        return {"kept": 0, "archived": 0, "pending": 0, "skipped": 0}
    prefix = os.path.basename(ledger_path) + ".shrink-"
    names = sorted(n for n in os.listdir(d)
                   if n.startswith(prefix) and os.path.isfile(os.path.join(d, n)))
    keep_idx = set(names[max(0, len(names) - SHRINK_KEEP_COUNT):])
    cutoff = time.time() - SHRINK_KEEP_DAYS * 86400.0
    cap = len(names) if max_files is None else max_files
    dst_dir = os.path.join(d, SHRINK_ARCHIVE_SUBDIR)
    kept = archived = pending = skipped = 0
    for n in names:
        src = os.path.join(d, n)
        try:
            st_src = os.stat(src)
        except OSError:
            continue
        # 保留门（"且"语义）：最新 N 份之内 且 mtime 在 D 天内 → 留原目录
        if n in keep_idx and st_src.st_mtime >= cutoff:
            kept += 1
            continue
        if archived >= cap:
            pending += 1        # 超单次上限，下轮 shrink 再清
            continue
        try:
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, n + ".gz")
            if os.path.exists(dst) and _gz_payload_bytes(dst) == st_src.st_size:
                os.remove(src)  # 断点续跑：归档已完整，仅摘原件
                archived += 1
                continue
            tmp = f"{dst}.tmp.{os.getpid()}.{os.urandom(3).hex()}"
            try:
                with open(src, "rb") as fi, gzip.open(
                        tmp, "wb", compresslevel=6) as fo:
                    shutil.copyfileobj(fi, fo, 1 << 20)
                    fo.flush()
                    os.fsync(fo.fileobj.fileno())
                if _gz_payload_bytes(tmp) != st_src.st_size:
                    os.remove(tmp)   # 校验不过：留原件待下轮
                    skipped += 1
                    continue
                os.replace(tmp, dst)
            except Exception:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                skipped += 1
                continue
            os.remove(src)      # 归档校验通过后才摘原件 = 移动语义
            archived += 1
        except Exception:
            skipped += 1
    return {"kept": kept, "archived": archived,
            "pending": pending, "skipped": skipped}


# 记忆分级（2026-11-17）：入库时打类型标签，召回时按优先级加权。
# 对齐业界做法（mem0 fact 分级 / Letta core-archival 分层）。
_MEMORY_HIGH_PATTERNS = (
    "教训", "铁律", "事故", "红线", "禁令", "禁止", "不许", "拍板",
    "根因", "预防", "L01", "L02", "L03", "L04", "L05", "L06", "L07",
    "L08", "L09", "L10", "L11", "L12", "L13", "L14",
)
_MEMORY_MED_PATTERNS = ("决策", "决议", "定案", "落定", "方案", "架构", "设计", "策略", "规矩")

def _classify_memory(obj, act, actual="", cur="") -> str:
    """记忆分级：lesson > decision > chatter。
    lesson=教训/铁律/事故/红线（高价值，召回优先）
    decision=决策/方案/策略（中价值）
    chatter=消息/日志/闲聊（默认）
    """
    text = f"{obj} {act} {actual} {cur}"
    for p in _MEMORY_HIGH_PATTERNS:
        if p in text:
            return "lesson"
    for p in _MEMORY_MED_PATTERNS:
        if p in text:
            return "decision"
    return "chatter"


def _sha1(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()


def _bigrams(chars: list) -> list:
    """中文大串无空格 ⇒ 整串成单 token 堵死部分匹配；补相邻双字治天花板。"""
    if len(chars) == 1:
        return [chars[0]]
    return ["".join(chars[i:i + 2]) for i in range(len(chars) - 1)]


def _tokens(sig: str) -> set:
    out = set()
    for t in (sig or "").replace("|", " ").replace("/", " ").split():
        if not t:
            continue
        out.add(t)
        run: list = []
        buf: list = []
        for ch in t:                      # CJK 连串补 bigram，拉丁串单列
            if "\u4e00" <= ch <= "\u9fff":
                if buf:
                    out.add("".join(buf))
                    buf = []
                run.append(ch)
            else:
                if run:
                    out.update(_bigrams(run))
                    run = []
                buf.append(ch)
        if run:
            out.update(_bigrams(run))
        if buf:
            out.add("".join(buf))
    return out


def _cover(q: set, e: set) -> float:
    """查询覆盖率：查询词有多少落在条目里（短查长条时比 Jaccard 敏感）。

    拉丁长 token 双向前缀匹配（两侧>=4 字符才比）：sz18x18 可命中 sz18x18to18x18
    （治 2026-11-04 合流实测天花板：形状 token 连写整串，前缀查询打不中）。
    短词护栏防 W5 式误命中；_sim（并账判据）不动 ⇒ 合并语义零变化。
    """
    if not q:
        return 0.0
    hit = 0
    for t in q:
        if t in e:
            hit += 1
            continue
        if len(t) >= 4 and any(len(x) >= 4 and (x.startswith(t) or t.startswith(x)) for x in e):
            hit += 1
    return hit / len(q)


_QUERY_SEG_SPLIT = re.compile(
    r"[\s，,。；;、？?！!：:（）()「」『』【】\[\]与和及跟同]+")
# ★ round-2 落线（2026-11-09）：连词（与/和/及/跟/同）入分段符——选对床 R1 实测
#   组合题 0/8→8/8；2026-11-07 分段修复只切标点，管不了并列连词
_URL_RE = re.compile(r"https?://\S+")   # P4 查询规整：URL 剥离（第六格）
_SEG_WINNERS = False  # H3 段冠军（2026-11-09 落地批）：H3-1 ✗ 零差异——本批
#   失败模式=门下缺失（真条压根不过 0.3 门）非挤出，重排救不了；按预注册回滚
#   默认关，代码留档待真正挤出型批次（撞出 top-4 边界）再开。
_MATCH_RAW = True   # R4a 匹配词面双层（2026-11-09 round-4）：压缩只压注入面，
#   不压匹配面——签名带原文（body_raw）保住话题词/判别词，治门下缺失。

# ★ H2' 值词锚冲突识别（2026-11-09 round-3）：冲突判据＝措辞近 **或**
#   双方有值词且值不同且话题重叠——抗压缩改写（round-2 实锤：压缩后真/干扰
#   词面拉开到 0.35，旧 0.6 门认不出冲突，高活性旧值顶位）。
_VAL_RE = re.compile(r"\d+(?:\.\d+)?\s*[^\d\s，。；;：:？?！!]{0,2}")


def _vals(s) -> list:
    return [re.sub(r"\s+", "", v) for v in _VAL_RE.findall(str(s or ""))]


def _conflict_pair(e1, e2) -> bool:
    """同题异值冲突判定（单源谓词，择新用）：措辞近(≥0.6) 或
    值词锚冲突（双方有值、值不同、话题重叠≥0.30）。bed 可 monkey-patch 对照。"""
    b1 = str(e1.get("signature", "")) + " " + str(e1.get("body", ""))
    b2 = str(e2.get("signature", "")) + " " + str(e2.get("body", ""))
    t1, t2 = _score_tokens(b1), _score_tokens(b2)
    if not t1 or not t2:
        return False
    if _cover(t1, t2) >= 0.6:
        return True
    v1, v2 = _vals(b1), _vals(b2)
    return bool(v1 and v2 and set(v1) != set(v2) and _cover(t1, t2) >= 0.30)


def _score_tokens(sig: str) -> set:
    """打分词面（2026-11-07 召回键修复）：CJK 多字词整词不入词面——bigram 已
    覆盖其全部可匹配粒度，整词入面只稀释查询覆盖率分母（实测「装库清单」查
    「装库记账」：共享 bigram「装库」＝1/3=0.33 过 0.30 门；整词入分母 1/4=0.25
    打空）。拉丁/单字整词保留；_tokens（并账判据 _sim 用）不动 ⇒ 合并语义零变化。"""
    out: set = set()
    for t in (sig or "").replace("|", " ").replace("/", " ").split():
        if not t:
            continue
        run: list = []
        buf: list = []
        cjk_multi = False
        for ch in t:
            if "\u4e00" <= ch <= "\u9fff":
                if buf:
                    out.add("".join(buf))
                    buf = []
                run.append(ch)
            else:
                if run:
                    if len(run) > 1:
                        cjk_multi = True
                    out.update(_bigrams(run))
                    run = []
                buf.append(ch)
        if run:
            if len(run) > 1:
                cjk_multi = True
            out.update(_bigrams(run))
        if buf:
            out.add("".join(buf))
        if not cjk_multi:
            out.add(t)
    return out


def _recall_sig(e: dict) -> str:
    """召回词面（2026-11-12 逐字抽取自 recall 内联段）：签名＋summary 正文/base
    兜底＋R4a body_raw 词面保真。_score_tokens 可按 eid 缓存其结果。"""
    sig = e.get("signature", "")
    if e.get("kind") == "summary":
        # 正文＋base 兜底（消费侧，2026-11-07 M3 实锤）：老条目签名＝决定句
        # （与查询词零叠），且账本只增不改不可重写——正文与 base 全量字段
        # （决定/数字/指针/教训，有损摘要压不掉的部分）一并参与匹配；
        # _cover 只看查询侧分母，加宽只会提高命中不会稀释。
        extra = str(e.get("body", ""))[:600]
        b = e.get("base") or {}
        if isinstance(b, dict):
            segs = [str(x) for v in b.values()
                    if isinstance(v, list) for x in v]
            extra += " " + "；".join(segs)[:400]
        if extra.strip():
            sig = sig + " " + extra
    if _MATCH_RAW and e.get("body_raw"):
        sig = sig + " " + str(e.get("body_raw", ""))[:600]  # R4a 词面保真
    return sig


def _sim(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ── 召回面分层（2026-11-07 M3 回声修复）──────────────────────
# ★ 键面 C+B（2026-11-15 拍板落地）：recall_good 三层回落——精确键→归一化键
#   →签名门控。存储零迁移（键仍是原文）、写侧零变化（feedback/撤销语义不动），
#   只改读侧命中面。门控 0.6＋唯一冠军＋值词锚冲突拒＋归一长度≥2（宁缺勿滥：
#   查表回落是零 token 直答，假阳代价≫漏答）。词面件与 recall 同源。
_GOOD_GATE = 1.0           # 签名门控下限（回放校准锁值：replay_out.json——FP=0 区间
                          # [0.95,1.00] TP=72 等效取保守端 1.00＝子集命中制；
                          # 0.6 设计初值被 composite 假阳否决，见 keyface_impl_report.md）
_PUNCT_STRIP = re.compile(r"[\W_]+")


def _good_norm(s) -> str:
    """归一化键（层 2）：NFKC＋去空白＋去标点＋小写——打字变体同键。"""
    s = unicodedata.normalize("NFKC", str(s or ""))
    return _PUNCT_STRIP.sub("", s).lower()


def _good_digits(s) -> set:
    r"""值词锚数字集（层 3 护栏）：\d+ 词集；双方有数且交空＝同题异值冲突。"""
    return set(re.findall(r"\d+", unicodedata.normalize("NFKC", str(s or ""))))


def _good_direct() -> bool:
    """灰度只读开关（2026-11-15 拍板）：缺省只读——命中只报不直答（观察一周），
    MEMGATE_GOOD_DIRECT=1 开直答。开关只影响**消费面直答**（gmem 直答/响应
    lookup_act），不影响读半边报告与命中事实/计数。"""
    return os.environ.get("MEMGATE_GOOD_DIRECT", "").strip() in ("1", "true", "on", "yes")


def _good_lookup(gp: dict, cur, gate=None):
    """三层回落查找（读侧）：精确键→归一化键（撞键取 ts 新者）→签名门控
    （score=max(Jaccard,查询覆盖率)≥gate＋唯一冠军＋值词锚不冲突＋归一长度≥2）。
    gate 缺省 _GOOD_GATE（回放校准锁值）；回放扫描可覆写。
    命中返回条目，未命中 None（explore 语义保留）。"""
    g = _GOOD_GATE if gate is None else gate
    key = str(cur)
    e = gp.get(key)
    if e is not None:
        return e
    nq = _good_norm(key)
    if len(nq) < 2:
        return None                      # 单字/空查询只走层 1
    best_ts = best = None                # 层 2：归一化键
    for k, v in gp.items():
        if _good_norm(k) == nq:
            ts = str((v or {}).get("ts", "")) if isinstance(v, dict) else ""
            if best is None or ts > best_ts:
                best_ts, best = ts, v
    if best is not None:
        return best
    qt = _score_tokens(key)              # 层 3：签名门控
    if not qt:
        return None
    qd = _good_digits(key)
    cands = []
    for k, v in gp.items():
        kt = _score_tokens(k)
        if not kt:
            continue
        kd = _good_digits(k)
        if qd and kd and not (qd & kd):
            continue                     # 值词锚冲突拒（37/38 一字之差语义全非）
        jac = len(qt & kt) / len(qt | kt)
        s = max(jac, _cover(qt, kt))
        if s >= g:
            cands.append((s, v))
    if not cands:
        return None
    cands.sort(key=lambda t: -t[0])
    if len(cands) > 1 and not (cands[0][0] > cands[1][0]):
        return None                      # 并列冠军＝不回落（宁缺勿滥）
    return cands[0][1]


def _entry_class(e: dict) -> str:
    """条目类别：summary=摘要层 / decision=决策入账层·rollup / transcript=转录审计层。

    回声修复判据（M3 试点实锤，2026-11-07）：自然查询会与自己的转录投递条目
    自匹配（同文 1.00 / 压缩查询 0.73 都实测过），回声对「省调用」零贡献还污染
    命中率口径。阈值法（只排『查询与正文近同』的）被证伪：压缩自匹配 0.727 与
    合法部分查询 0.75 分数交织不可分阈，且同文自匹配与合法内容查询完全同形
    （都可 1.00）⇒ 只能按**条目来源类**分，不按分数分。
    识别不改账：按写入面既有标记（kind / provenance via=contextEngine.* /
    obj·签名前缀 msg:·turn|），旧账零重写即可归类。
    ★ rollup 必须先判：compact rollup 签名是归档条目签名并集、可能以 msg: 开头，
    按前缀判会把「召回覆盖件」误杀成转录（砸「召回覆盖不塌」）。"""
    if e.get("kind") == "summary":
        return "summary"
    if e.get("rollup"):
        return "decision"
    if e.get("kind") == "transcript":
        return "transcript"
    if any(str(p.get("via") or "").startswith("contextEngine.")
           for p in (e.get("provenance") or []) if isinstance(p, dict)):
        return "transcript"      # ingest/commit 的固有写入面（实测 1656/1656 覆盖）
    obj = str(e.get("obj") or "")
    sig = str(e.get("signature") or "")
    if obj.startswith("msg:") or obj == "turn" or sig.startswith(("msg:", "turn|")):
        return "transcript"      # 前缀兑底（provenance 被剥的条目）
    return "decision"


def _txnal(fn):
    """写事务装饰器（2026-11-07）：mutator ＝ 持锁·读最新·改·出口提交。
    并账合写已废——merge 会把已撤销/已搬走条目从磁盘吸回来（回归④实锤）。"""
    def wrapper(self, *args, **kwargs):
        with self._txn():
            return fn(self, *args, **kwargs)
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


class _EntryDict(dict):
    """单条条目（2026-11-12）：字段级直改打脏标记——旧语义=事务重读把未落盘
    的字段级直改也冲掉；跳读后靠打脏保真。内部保活/回放用 _lv_set_quiet
    绕过（另有持久通道，不打脏）。"""
    __slots__ = ("_store",)

    def _dirty(self):
        st = self._store
        if st is not None:
            st._entries_dirty = True

    def __setitem__(self, k, v):
        self._dirty()
        super().__setitem__(k, v)

    def __delitem__(self, k):
        self._dirty()
        super().__delitem__(k)

    def pop(self, *a):
        self._dirty()
        return super().pop(*a)

    def popitem(self):
        self._dirty()
        return super().popitem()

    def clear(self):
        self._dirty()
        super().clear()

    def update(self, *a, **kw):
        self._dirty()
        super().update(*a, **kw)

    def setdefault(self, *a):
        self._dirty()
        return super().setdefault(*a)


def _lv_set_quiet(e: dict, v: float) -> None:
    """静默写 liveness（不打脏）：保活提升/日志回放专用——持久化另走
    _persist_liveness/全量写，打脏会迫使下拍全量重读白擕缓存。"""
    dict.__setitem__(e, "liveness", v)


class _EntriesDict(dict):
    """entries 字典（2026-11-12 stat 跳读配套）：条目级增删/替换打脏标记。
    语义守恒：旧语义=事务内 _reload_disk 整体重读把『未落盘的直改 st.entries』
    冲掉（select_eval 冒烟实锤）；stat 跳读后靠脏标记保真——脏了照旧全量
    重读冲掉（同旧语义），不脏且主文件未变才跳（内存==磁盘，冲无可冲）。
    字段级直改由 _EntryDict 同步打脏（2026-11-12 补全）：两类直改不 save()
    都会被下拍重读冲掉，与旧语义逐字一致。"""
    __slots__ = ("_store",)

    def _dirty(self):
        st = self._store
        if st is not None:
            st._entries_dirty = True

    def _wrap(self, v):
        if isinstance(v, dict) and not isinstance(v, _EntryDict):
            v = _EntryDict(v)
            v._store = self._store
        return v

    def __setitem__(self, k, v):
        self._dirty()
        super().__setitem__(k, self._wrap(v))

    def __delitem__(self, k):
        self._dirty()
        super().__delitem__(k)

    def pop(self, *a):
        self._dirty()
        return super().pop(*a)

    def popitem(self):
        self._dirty()
        return super().popitem()

    def clear(self):
        self._dirty()
        super().clear()

    def update(self, *a, **kw):
        for src in a:
            for k, v in (src.items() if hasattr(src, "items") else src):
                self[k] = v
        for k, v in kw.items():
            self[k] = v

    def setdefault(self, k, default=None):
        if k not in self:
            self[k] = default
        return self[k]


class LandingStore:
    """落点账本：JSON 硬落盘＋签名门控召回＋同构合并＋provenance。"""

    def __init__(self, path: Optional[str] = None):
        self.path = path or DEFAULT_PATH
        self._entries: Dict[str, dict] = _EntriesDict()
        self._entries._store = self
        self._entries_dirty = False     # 内存 entries 可能≠磁盘（未落盘直改/进行中事务）
        self.meta: Dict[str, Any] = {}
        self.good_patterns: Dict[str, dict] = {}   # good 答案模式（A14 机制本体）
        self._corrupt = False                      # 损坏封写标志（机制修复 2026-11-07）
        self._depth = 0                            # 写事务嵌套深度
        self._pending = False                      # 事务内待提交标记
        self._scache = {}        # 召回词面缓存 eid→[cls, et]（2026-11-12；内容变更失效）
        self._disk_sig = None    # 主文件 (dev,ino,size,mtime_ns) 跳读指纹
        self._lvj_lines = 0      # 保活提升日志数据行数（超阈并回主文件）
        self._lvj_sig = None     # 保活提升日志 stat 备忘（未变则跳重读）
        self._load()

    @property
    def entries(self) -> Dict[str, dict]:
        return self._entries

    @entries.setter
    def entries(self, value) -> None:
        d = _EntriesDict()
        d._store = self
        self._entries = d
        for k, v in value.items():
            d[k] = v          # 走 __setitem__：值包装 _EntryDict＋打脏
        self._entries_dirty = True

    # ── 生死层 ────────────────────────────────────────────
    def _load(self) -> None:
        """构造装卷（持锁·读最新·补时间拍）；时间拍的落盘随其后的事务提交。"""
        with self._lock():
            self._depth += 1
            try:
                self._reload_disk()
                self._time_tick()      # 开账先补时间拍：闲置期的衰减在此入账
                self._flush()          # 时间拍落盘
            finally:
                self._depth -= 1

    def _lock(self):
        """跨进程排他锁（fcntl.flock）——读-改-写事务串行化（机制修复 2026-11-07）。"""
        import contextlib

        @contextlib.contextmanager
        def _cm():
            lock_path = self.path + ".lock"
            dd = os.path.dirname(lock_path)
            if dd:
                os.makedirs(dd, exist_ok=True)
            fh = open(lock_path, "a")
            locked = False
            try:
                try:
                    import fcntl
                    fcntl.flock(fh, fcntl.LOCK_EX)
                    locked = True
                except ImportError:
                    pass                 # 非 POSIX：退化为无锁（单写者场景）
                yield
            finally:
                if locked:
                    try:
                        fcntl.flock(fh, fcntl.LOCK_UN)
                    except OSError:
                        pass
                fh.close()
        return _cm()

    def _reload_disk(self) -> None:
        """读最新（写事务第一步）：内存态整体替换为磁盘态。
        并账合写已废（2026-11-07）：merge 会把已撤销/已搬走的条目从磁盘
        吸回来（回归④撤销保守回退实锤）——删除语义只有『整体替换』守得住。
        stat 跳读（2026-11-12 召回热路径）：一切写入持本锁，同锁下主文件
        (dev,ino,size,mtime_ns) 与上次读写一致＝其间无写入，跳过全量重解析；
        stat 有变才整体替换。保活提升日志每拍并入（只增合并，_lvj_read）。"""
        sig = self._stat_sig()
        if (sig is not None and sig == self._disk_sig
                and not self._entries_dirty):
            self._lvj_read()         # 主文件未变且内存干净：只并其他进程的保活提升
            return
        self.entries = {}
        self.meta = {}
        self.good_patterns = {}
        self._scache.clear()
        self._disk_sig = None
        self._lvj_sig = None   # 内存重置：日志必须重放（备忘作废，防提升丢失）
        if not os.path.exists(self.path):
            self._lvj_read()
            self._entries_dirty = False   # 空内存==无盘文件，冲无可冲
            return
        if os.path.getsize(self.path) == 0:
            self._disk_sig = self._stat_sig()
            self._lvj_read()
            self._entries_dirty = False
            return                  # 新账本（空文件）＝正常起步，非损坏
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for e in data.get("entries", []):
                if isinstance(e, dict) and e.get("id"):
                    self.entries[e["id"]] = e
            self.meta = data.get("meta", {}) if isinstance(data.get("meta", {}), dict) else {}
            gp = data.get("good_patterns", {})
            self.good_patterns = gp if isinstance(gp, dict) else {}
            self._disk_sig = self._stat_sig()
        except (json.JSONDecodeError, OSError):
            # 真损坏：留证＋封写（防"空账重启→覆写全账"重演；
            # 人工恢复后 save(force=True) 显式放行）
            import sys
            import time as _t
            self._corrupt = True
            keep = self.path + ".corrupt-" + _t.strftime("%Y%m%d-%H%M%S")
            try:
                os.replace(self.path, keep)
                print(f"[landing] 账本损坏：已留证 {keep}，封写待人工恢复: {self.path}",
                      file=sys.stderr)
            except OSError:
                print(f"[landing] 账本损坏：封写待人工恢复: {self.path}", file=sys.stderr)
            return
        self._lvj_read()
        self._entries_dirty = False   # 全量装载完成＝内存==磁盘（未落盘直改被冲掉，同旧语义）

    @contextlib.contextmanager
    def _txn(self):
        """写事务（机制核心）：持锁 → 读最新 → 改 → 提交。
        嵌套（如 deposit 内的自动合账）复用外层锁，出口统一提交一次。"""
        cm = self._lock() if self._depth == 0 else None
        if cm is not None:
            cm.__enter__()
        self._depth += 1
        try:
            if self._depth == 1:
                self._reload_disk()   # 读最新：丢弃旧快照，杜绝覆写/复活
            yield
        finally:
            self._depth -= 1
            if self._depth == 0:
                self._flush()         # 改完写
            if cm is not None:
                cm.__exit__(None, None, None)

    def _flush(self) -> None:
        if not self._pending:
            return
        self._pending = False
        self._write_now()

    def _write_now(self, force: bool = False) -> None:
        """持锁原子写：唯一 tmp＋fsync＋replace＋缩水护栏（P0 修复层）。"""
        if self._corrupt and not force:
            raise self._corrupt_err()
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        made = False
        old_sz = 0
        try:
            old_sz = os.path.getsize(self.path) if os.path.exists(self.path) else 0
        except OSError:
            pass
        tmp = f"{self.path}.tmp.{os.getpid()}.{os.urandom(3).hex()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"entries": list(self.entries.values()), "meta": self.meta,
                       "good_patterns": self.good_patterns},
                      f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        try:
            # 缩水护栏（2026-11-13 修误报）：按**实际新文件字节**判缩水——
            # 旧口径 est=条数×300 对摘要重条目账本（实测 ~980B/条）恒低估 ⇒
            # 每次 save 都误判缩水、留一份 15MB 全量快照（实证 21 小时 3000 份/7.5GB）。
            new_sz = os.path.getsize(tmp)
            if old_sz > 50_000 and old_sz > 3 * new_sz:
                import shutil
                import time as _t
                shutil.copy2(self.path,
                             self.path + ".shrink-" + _t.strftime("%Y%m%d-%H%M%S"))
                made = True     # 本收缩留了写史 → 出口顺手做保留清扫
        except OSError:
            pass                    # 护栏失败不阻写
        os.replace(tmp, self.path)
        self._lvj_clear()                  # 保活提升已并入主文件：清追加日志
        self._disk_sig = self._stat_sig()
        self._entries_dirty = False        # 落盘成功＝内存==磁盘
        if made:
            try:
                sweep_shrink_snapshots(
                    self.path, max_files=SHRINK_SWEEP_MAX_PER_CALL)
            except Exception:
                pass                # 保留清扫失败不阻写（下轮 shrink 再清）

    # ── 召回热路径支撑（2026-11-12，见模块头 LIVENESS_JOURNAL_* 注释）───
    def _corrupt_err(self) -> RuntimeError:
        return RuntimeError(
            f"账本损坏封写：{self.path} 已损坏（留证 .corrupt-*），拒绝写入防覆写；"
            f"人工恢复后用 save(force=True) 显式放行")

    def _stat_sig(self):
        """主文件 stat 指纹 (dev,ino,size,mtime_ns)；不存在返回 None。"""
        try:
            st = os.stat(self.path)
        except OSError:
            return None
        return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)

    def _lvj_path(self) -> str:
        return self.path + LIVENESS_JOURNAL_SUFFIX

    def _lvj_clear(self) -> None:
        try:
            os.remove(self._lvj_path())
        except OSError:
            pass                # 清不掉不阻写：epoch 不符时 _lvj_read 会整卷作废（自愈）
        self._lvj_sig = None

    def _lvj_read(self) -> int:
        """保活提升日志并入内存态（只增合并 max）。epoch 校验：日志头记创建时
        主文件指纹，不符＝主文件已被整体换新（复制覆盖/全量写后未清残卷）——
        旧保活随旧内容作废（与旧语义一致：换文件即丢旧提升）；全量写后未清
        的残卷也在此自愈（值已并入主文件，丢弃无损）。返回并入条数。
        stat 备忘（2026-11-12）：日志未变且主文件未变（同锁下）＝无新提升，
        跳重读防 O(n²) 重放；全量装载路径重置备忘（内存重置后必须重放）。"""
        p = self._lvj_path()
        try:
            st = os.stat(p)
            sig = (st.st_size, st.st_mtime_ns)
        except OSError:
            self._lvj_sig = None
            self._lvj_lines = 0
            return 0
        if sig == self._lvj_sig:
            return 0               # 日志未变：上拍已并过（内存含提升）
        self._lvj_sig = sig
        try:
            with open(p, "r", encoding="utf-8") as f:
                raw = f.read().splitlines()
        except OSError:
            self._lvj_sig = None
            return 0
        lines = [ln for ln in raw if ln.strip()]
        if not lines:
            self._lvj_lines = 0
            return 0
        try:
            head = json.loads(lines[0])
        except ValueError:
            head = None
        ep = self._stat_sig()
        ok = (isinstance(head, dict) and "_epoch" in head and ep is not None
              and head["_epoch"] == list(ep))
        if not ok:
            try:
                os.remove(p)     # 无 epoch 头/损坏/主文件已换新：整卷作废（保活可丢，条目不丢）
            except OSError:
                pass
            self._lvj_sig = None
            self._lvj_lines = 0
            return 0
        self._lvj_lines = len(lines) - 1
        n = 0
        for ln in lines[1:]:
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            for k, v in d.items():
                e = self.entries.get(k)
                if e is None:
                    continue
                try:
                    nv = float(v)
                except (TypeError, ValueError):
                    continue
                if nv > float(e.get("liveness", 1.0)):
                    _lv_set_quiet(e, nv)   # 日志回放＝持久已确认，不打脏
                    n += 1
        return n

    def _lvj_append(self, bumps: dict) -> None:
        """保活提升追加（值即持久）：绝对值只增，append+fsync。日志首行记
        epoch（主文件指纹）；后续追加不重记。超 MERGE_AT 行自动全量并回有界。"""
        if not bumps:
            return
        p = self._lvj_path()
        lines = []
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            ep = self._stat_sig()
            if ep is None:
                # 主文件不存在：无法建立 epoch，退化为全量写（重建主文件，近旧语义）
                self.save()
                return
            lines.append(json.dumps({"_epoch": list(ep)}))
        for eid, lv in bumps.items():
            lines.append(json.dumps({str(eid): float(lv)}))
        data = ("\n".join(lines) + "\n").encode("utf-8")
        fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        self._lvj_lines += len(bumps)
        try:
            st = os.stat(p)
            self._lvj_sig = (st.st_size, st.st_mtime_ns)   # 自己刚追加：不必下拍重读
        except OSError:
            self._lvj_sig = None
        if self._lvj_lines > LIVENESS_JOURNAL_MERGE_AT:
            self.save()            # 超阈并回主文件＋清日志（事务内＝出口统一写）

    def _persist_liveness(self, bumps: dict) -> None:
        """保活提升落盘（2026-11-12 召回热路径）：值即持久（追加日志+fsync），
        与旧『save 全量重写』同等持久语义；全量写时并回主文件。封写守卫同律。"""
        if self._corrupt:
            raise self._corrupt_err()
        self._lvj_append(bumps)

    def save(self, force: bool = False) -> None:
        """硬落盘——落点铁律：写即持久。
        事务内＝延迟提交（出口统一写一次）；事务外＝持锁写当前内存（兼容旧调用方）。
        机制修复（2026-11-07 P0）：mutator 走写事务（持锁·读最新·改·写），
        此前的"并账合写"已废——merge 会复活已撤销/已搬走条目（回归④实锤）。"""
        if self._corrupt and not force:
            raise self._corrupt_err()
        if self._depth > 0 and not force:
            self._pending = True
            return
        with self._lock():
            self._write_now(force=force)

    @_txnal
    def deposit(self, obj: Any = None, act: Any = None, actual: Any = None,
                cur: Any = None, via: str = "calldecay.learn",
                extra: Optional[dict] = None) -> dict:
        """入账即落盘（A2 病根修复）。同构合并：sha1 相同或签名 Jaccard≥0.9 并账。"""
        self._scache.clear()   # 内容变更（provenance 增长可改 cls）：词面缓存整体失效
        sig = f"{obj}|{act}"
        content = f"{obj}|{act}|{actual}|{cur}"
        eid = _sha1(content)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        prov = {"via": via, "ts": now}
        if extra:
            prov.update(extra)

        if eid in self.entries:
            e = self.entries[eid]
            e["hits"] = int(e.get("hits", 1)) + 1
            e["liveness"] = 1.0                       # 保活：复现即回前排
            e.setdefault("provenance", []).append(prov)
            self.save()
            self._maybe_auto_compact()
            return e

        for e in self.entries.values():               # 同构合并（防膨胀）
            if _sim(sig, e.get("signature", "")) >= MERGE_SIM:
                e["hits"] = int(e.get("hits", 1)) + 1
                e["liveness"] = 1.0
                e.setdefault("provenance", []).append({**prov, "merged": content})
                self.save()
                self._maybe_auto_compact()
                return e

        # 记忆分级（2026-11-17）：入库时打类型标签，召回时按优先级加权。
        # 对齐业界做法（mem0 fact 分级 / Letta core-archival 分层）。
        _MEMORY_TYPE = _classify_memory(obj, act, actual, cur)
        entry = {"id": eid, "obj": obj, "act": act, "actual": actual, "cur": cur,
                 "signature": sig, "hits": 1, "liveness": 1.0,
                 "provenance": [prov], "ts": now, "memory_type": _MEMORY_TYPE}
        self.entries[eid] = entry
        entry = self.entries[eid]   # 返回店内包装对象（值身份语义同旧）
        self.save()
        self._maybe_auto_compact()   # 条数过阈自动合账（2026-11-04 补空档）
        return entry

    # ── 排序层（A3：衰减只管顺序，不管生死）────────────────
    @_txnal
    def recall(self, query_signature: str, k: int = 8,
               gate: float = RECALL_GATE,
               min_liveness: float = MIN_LIVENESS,
               include_transcripts: bool = False,
               now: Optional[str] = None,
               rescue: bool = True,
               strip_urls: bool = False) -> List[dict]:
        """strip_urls 默认关（2026-11-09 五连跑实测 -2：URL 词面对部分查询有匹配
        贡献，剥离过头；参数留着前瞻批次再校）。rescue=P3 量门复活（暖空才捞冷）。"""
        """签名门控召回：max(Jaccard, 查询覆盖率, 分段覆盖率) ≥ gate **且**
        liveness ≥ min_liveness 才出账；多话题查询按分段取最大覆盖（2026-11-07
        召回键修复：整体覆盖率惩罚多话题查询，「装库清单 会影响 后台任务 吗」
        实测 1/12≈0.08 打空）；按 (相似度, liveness) 排序；被召回即保活。

        min_liveness＝「越用越省」的量门（2026-11-04 重立）：冷条目**不注入**——
        不注≠删：账上仍在，同构复现入账即回前排；replay/compact/restore 全量可取。
        ★补丁①（2026-11-12 落地）：decision 拍板层免量门（9/9 低频关键拍板被流放
        是实锤机制伤），summary/transcript 照旧受量门。

        召回面分层（2026-11-07 M3 回声修复，判据见 _entry_class）：转录类条目
        默认**不入召回面**——自然查询必与自己的转录投递条目自匹配（同文 1.00/
        压缩 0.73 实测），回声≠召回价值。排除≠删除：条目原样在账，replay/compact/
        restore 照旧；include_transcripts=True 走显式审计面（治「存得进捞不出」，
        W2/W3 回归口径迁移在此）。summary 与普通 deposit 召回行为逐字不变。
        新鲜度缺口（尚未摘要的新内容）由摘要引擎兑底——摘要条目在默认面可召回。
        """
        if strip_urls:
            query_signature = _URL_RE.sub(" ", query_signature)  # P4：URL 不参与匹配
        qt = _score_tokens(query_signature)
        seg_qts = [x for x in (_score_tokens(s) for s in
                   _QUERY_SEG_SPLIT.split(query_signature)) if x]
        scache = self._scache          # 词面缓存（2026-11-12）：cls/et 按 eid 复用
        scored = []
        for e in self.entries.values():
            if now is not None and str(e.get("ts", "")) > str(now):
                continue                      # J2b 时间可得性（2026-11-09 落线）：
                                              #   传 now 则未来件不出召回面（计划类
                                              #   查询不传 now 即可取未来件）
            hit = scache.get(e.get("id"))
            if hit is None:
                hit = [_entry_class(e), None]
                scache[e.get("id")] = hit
            cls = hit[0]
            if cls == "transcript" and not include_transcripts:
                continue                      # 回声杀死：转录类默认不入召回面（排除≠删除）
            if cls != "decision" and float(e.get("liveness", 1.0)) < min_liveness:
                continue                      # 冷条目不注入（不注≠删）；★补丁①（11-12）：
                                              #   decision 拍板层免量门（低频关键拍板
                                              #   不再被流放），summary 照旧受量门
            et = hit[1]
            if et is None:
                et = _score_tokens(_recall_sig(e))
                if cls != "transcript":
                    hit[1] = et       # 转录面仅显式审计时用，用完即弃防缓存膨胀
            jac = (len(qt & et) / len(qt | et)) if qt and et else 0.0
            s = max([jac, _cover(qt, et)]
                    + [_cover(sq, et) for sq in seg_qts])
            if s >= gate:
                scored.append((s, float(e.get("liveness", 1.0)), e, et))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        # ★ P3 量门复活通道（2026-11-09 第六格落线，M3 实锤：365 条摘要 liveness
        #   全 0.01 被量门流放、对口记忆 0.400 拦在召回面外）：暖通道空才捞冷，
        #   「越用越省」不破——暖有货不注入冷；冷条目被召回即保活复温（原有语义）。
        if not scored and rescue and min_liveness > 0:
            return self.recall(query_signature, k=k, gate=gate,
                               min_liveness=0.0,
                               include_transcripts=include_transcripts, now=now,
                               rescue=False, strip_urls=False)
        # ★ 冲突择新（2026-11-09 round-2 落线；round-3 换 H2' 谓词）：
        #   同题异值冲突时 ts 新者胜——旧高活性值不压新值。
        #   只动 top-2 冲突对，普通查询零影响；未来件拦不住（那是 J2b 的活）。
        if len(scored) >= 2:
            e1, e2 = scored[0][2], scored[1][2]
            if _conflict_pair(e1, e2) \
                    and str(e1.get("ts", "")) < str(e2.get("ts", "")):
                scored[0], scored[1] = scored[1], scored[0]
        out = []
        bumped = []      # (entry, new_lv)：先持久后应用（2026-11-12），持久失败不留内存残留
        # ★ H3 段冠军前置（2026-11-09 落地批，land3_prereg_v1.md）：输出序＝
        #   [全局 top-1]＋[各分段覆盖冠军（同覆盖取新 ts）]＋[其余]——组合查询
        #   真条防挤出；单段查询冠军=top-1 恒等（直取零变化，H3-2 守）。
        ordered = scored
        if _SEG_WINNERS and seg_qts and len(scored) > 1:
            win, seen = [], set()
            for sq in seg_qts:
                best = max(scored, key=lambda t: (_cover(sq, t[3]),
                                                  str(t[2].get("ts", ""))))
                if id(best[2]) not in seen:
                    seen.add(id(best[2]))
                    if best is not scored[0]:
                        win.append(best)
            ordered = ([scored[0]] + win
                       + [t for t in scored[1:] if id(t[2]) not in seen])
        for s, _lv, e, _et in ordered[:k]:
            new_lv = min(1.0, float(e.get("liveness", 1.0)) + 0.1)
            bumped.append((e, new_lv))
            out.append({"entry": e, "score": round(s, 3), "liveness": new_lv,
                        "class": scache.get(e.get("id"), [None])[0] or _entry_class(e)})
        if bumped:
            for e, new_lv in bumped:
                _lv_set_quiet(e, new_lv)    # 先应用（同旧序）：静默写不打脏
            self._persist_liveness(
                {str(e.get("id")): float(lv) for e, lv in bumped})  # 值即持久（追加日志）
        return out

    # ── 摘要入账（memory-as-context 入口段，2026-11-06 实现稿 v1）────
    @_txnal
    def deposit_summary(self, topic: str, body: str, source_anchor: str,
                        via: str = "summarize.engine", base: Optional[dict] = None) -> dict:
        """摘要入账（kind=summary）：**来源锚必带，无锚拒收**（摘要污染守则硬闸，T1）。
        入账即定稿：同锚再入只并账（hits+1，正文不改），防双重压缩（T5 上游另有
        feed 短路）；签名=话题词，与普通条目同轨走 recall（T4）。
        base=全量底稿（T8）：**body 可坏、base 不坏**——垃圾/罢工输出下事实仍
        可指回，可 revoke 回退 base 版。"""
        self._scache.clear()   # 内容变更：词面缓存整体失效
        if not (source_anchor or "").strip():
            self.meta["summary_rejected"] = int(self.meta.get("summary_rejected", 0)) + 1
            self.save()
            return {"rejected": "source_anchor required"}
        sig = str(topic or "")
        eid = _sha1(f"summary|{source_anchor}")   # 同锚同条：重复入账并账不重写
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        prov = {"via": via, "ts": now}
        if eid in self.entries:
            e = self.entries[eid]
            e["hits"] = int(e.get("hits", 1)) + 1
            e["liveness"] = 1.0
            e.setdefault("topic", sig)    # #4 旧条目补字段：主题可见于条目
            e.setdefault("provenance", []).append(prov)   # 定稿：body 不改
            self.save()
            return e
        for e in self.entries.values():           # MERGE_SIM 去重合账（只并不改）
            if e.get("kind") == "summary" and _sim(sig, e.get("signature", "")) >= MERGE_SIM:
                e["hits"] = int(e.get("hits", 1)) + 1
                e["liveness"] = 1.0
                e.setdefault("topic", sig)
                e.setdefault("provenance", []).append({**prov, "merged": eid})
                self.save()
                return e
        entry = {"id": eid, "kind": "summary", "signature": sig, "body": body,
                 "topic": sig,   # #4 主题落条目字段（此前只进签名，检索面看不到）
                 "source_anchor": source_anchor, "base": base or {},
                 "hits": 1, "liveness": 1.0,
                 "provenance": [prov], "ts": now}
        self.entries[eid] = entry
        entry = self.entries[eid]   # 返回店内包装对象（值身份语义同旧）
        self.save()
        self._maybe_auto_compact()
        return entry

    # ── good 答案模式沉淀（2026-11-05 G/S 系列 A/B 验证的机制本体）──
    # Good pattern minimum verification threshold (2026-11-18 增量, 判据补批 2026-11-19 合流)
    GOOD_MIN_N = 3  # Need 3 confirmations before pattern is trusted

    @_txnal
    def feedback(self, cur, act, ok: bool = True) -> dict:
        """结果确认接口（生产反馈＝任务奖励/结果确认，非评估器）。
        ok=True: 沉淀/覆盖 cur→act（验证语义=最近一次 good 答案接管回落段；
        计数 n 累计）。ok=False: 撤销——仅当当前模式正是 act（保守扩展：撤销
        只会退回 explore，不会留错答案）。入账即落盘（与 deposit 同律）。
        A/B 证据：G1 100%vs42.4%(oracle)；S1 稀疏20=100%；S2 噪声10=79.9%。"""
        key = str(cur)
        if ok:
            n = int(self.good_patterns.get(key, {}).get("n", 0)) + 1
            verified = n >= self.GOOD_MIN_N
            self.good_patterns[key] = {"act": act, "n": n, "verified": verified,
                                       "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
            self.meta["good_ok"] = int(self.meta.get("good_ok", 0)) + 1
            self.save()
            return self.good_patterns[key]
        e = self.good_patterns.get(key)
        if e and e.get("act") == act:
            del self.good_patterns[key]
            self.meta["good_revoke"] = int(self.meta.get("good_revoke", 0)) + 1
            self.save()
            return {"revoked": key}
        return {"revoked": None}

    @_txnal
    def recall_good(self, cur):
        """零 token 高质回落（读半边＝报告面）：命中返回沉淀动作，未命中 None。
        键面 C+B（2026-11-15 拍板）：精确键→归一化键→签名门控三层回落
        （_good_lookup；存储零迁移、写侧零变化）。
        灰度只读（缺省）：**命中只报不直答**——读半边照常报出命中（含
        good_shadow_hits 灰度命中计数），直答门在消费面（adapter.decide 的
        gmem 直答 / serve.decide 的响应）按 _good_direct() 收口；
        MEMGATE_GOOD_DIRECT=1 开直答（观察一周后）。
        计数（good_queries/good_hits）随写事务落盘——原"桥侧负责落盘"并入
        事务（2026-11-07）：计数不再依赖外部 save，进程崩溃不蒸发。"""
        self.meta["good_queries"] = int(self.meta.get("good_queries", 0)) + 1
        e = _good_lookup(self.good_patterns, cur)
        act = e.get("act") if isinstance(e, dict) else (str(e) if e is not None else None)
        # 直答门真化（判据补批 2026-11-19）：灰度报告照旧（F26 语义），直答须过 GOOD_MIN_N 验证
        if act is not None and _good_direct() and isinstance(e, dict) and not e.get("verified", False):
            act = None
        if e is not None:
            self.meta["good_hits"] = int(self.meta.get("good_hits", 0)) + 1
            if not _good_direct():
                self.meta["good_shadow_hits"] = int(
                    self.meta.get("good_shadow_hits", 0)) + 1
        self.save()
        return act

    @_txnal
    def decay(self, factor: float = DECAY_FACTOR) -> None:
        """活性衰减（A3）：只降排序权重，**永不删条目**。"""
        for e in self.entries.values():
            e["liveness"] = round(max(0.01, float(e.get("liveness", 1.0)) * factor), 4)
        self.meta["last_decay_ts"] = time.time()   # 入账拍落地：时间拍从此刻重计
        self.save()

    def _time_tick(self, now: Optional[float] = None) -> int:
        """时间拍（2026-11-04 补空档）：闲置时钟也走——每 TICK_SECONDS 一拍。
        与入账拍同系数叠加（活跃=入账拍＋时间拍，闲置=只有时间拍）；
        只降 liveness，不删条目（铁律不变）；0 拍零写盘。"""
        now = time.time() if now is None else now
        last = float(self.meta.get("last_decay_ts", now))
        ticks = int((now - last) // TICK_SECONDS)
        if ticks <= 0:
            return 0
        f = DECAY_FACTOR ** ticks
        for e in self.entries.values():
            e["liveness"] = round(max(0.01, float(e.get("liveness", 1.0)) * f), 4)
        self.meta["last_decay_ts"] = last + ticks * TICK_SECONDS
        self.save()
        return ticks

    def _maybe_auto_compact(self) -> dict:
        """冷层自动合账（2026-11-04 补空档）：条数过阈即按保守三口径搬冷旧条目。
        触发间隔＝阈值半幅（防每次入账重扫）；零命中也只调到下次溢出才重试。"""
        nxt = int(self.meta.get("next_auto_compact_at", AUTO_COMPACT_AT))
        if len(self.entries) < nxt:
            return {}
        r = self.compact()
        self.meta["next_auto_compact_at"] = len(self.entries) + max(1, AUTO_COMPACT_AT // 2)
        self.save()
        return r

    # ── 冷层合账归档（compaction：可逆，不是删除）──────────
    def _archive_path(self) -> str:
        base = self.path[:-5] if self.path.endswith(".json") else self.path
        return base + ".archive.json"

    def _archive_load(self) -> List[dict]:
        ap = self._archive_path()
        if not os.path.exists(ap) or os.path.getsize(ap) == 0:
            return []
        try:
            with open(ap, "r", encoding="utf-8") as f:
                return [e for e in json.load(f).get("entries", []) if isinstance(e, dict)]
        except (json.JSONDecodeError, OSError):
            import sys
            print(f"[landing] 归档件损坏/不可读，空归档继续: {ap}", file=sys.stderr)
            return []

    def _archive_save(self, arc: List[dict]) -> None:
        ap = self._archive_path()
        d = os.path.dirname(ap)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = f"{ap}.tmp.{os.getpid()}.{os.urandom(3).hex()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"entries": arc}, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ap)

    @_txnal
    def compact(self, liveness_max: float = 0.6, hits_max: int = 1,
                min_age_days: float = 7.0) -> dict:
        """冷条目（旧＋低活＋低命中）搬入归档件，主账留一条 rollup 保召回覆盖。

        与 decay 的边界（铁律「条目永不因衰减删除」不受触碰）：
        decay 只降排序权重；compact 是**显式搬账**——条目逐字入 landing.archive.json，
        rollup 的 provenance 记 archived_ids＋口径，restore() 可整批取回，语义零丢失。
        口径三连（默认值即保守盘）：liveness≤上限 且 hits≤上限 且 账龄≥下限。
        """
        self._scache.clear()   # 条目增删（搬账/rollup）：词面缓存整体失效
        import time as _time
        now_s = _time.strftime("%Y-%m-%dT%H:%M:%S")
        cutoff = _time.time() - min_age_days * 86400

        def _age_ok(e: dict) -> bool:
            try:
                t = _time.mktime(_time.strptime(str(e.get("ts", "")), "%Y-%m-%dT%H:%M:%S"))
            except (ValueError, OverflowError):
                return False      # ts 不可解析＝口径存疑，不入盘（拿不准不压）
            return t <= cutoff

        cold = [e for e in list(self.entries.values())
                if float(e.get("liveness", 1.0)) <= liveness_max
                and int(e.get("hits", 1)) <= hits_max
                and _age_ok(e)]
        if not cold:
            return {"archived": 0, "n_main": len(self.entries),
                    "n_archive": len(self._archive_load())}

        arc = self._archive_load()
        ids = []
        for e in cold:
            arc.append(e)
            ids.append(e["id"])
            self.entries.pop(e["id"], None)
        self._archive_save(arc)

        # rollup：召回覆盖不塌（签名=代表签名并集，有界 15 条）
        sigs = [str(e.get("signature", "")) for e in cold if e.get("signature")][:15]
        rollup = {
            "id": _sha1(f"compact-rollup|{now_s}|{len(cold)}"),
            "obj": "archive:rollup", "act": f"compact {len(cold)} 条",
            "actual": f"liveness<={liveness_max}, hits<={hits_max}, age>={min_age_days}d",
            "cur": "landing.compact",
            "signature": "|".join(sigs),
            "hits": 1, "liveness": 0.5,
            "provenance": [{"via": "landing.compact", "ts": now_s,
                            "archived_ids": ids,
                            "criteria": {"liveness_max": liveness_max,
                                         "hits_max": hits_max,
                                         "min_age_days": min_age_days}}],
            "ts": now_s, "rollup": True,
        }
        self.entries[rollup["id"]] = rollup
        self.save()
        return {"archived": len(ids), "n_main": len(self.entries),
                "n_archive": len(arc), "rollup_id": rollup["id"]}

    @_txnal
    def restore(self, rollup_id: Optional[str] = None) -> dict:
        """compact 的逆操作：取回归档条目（逐字），rollup 随之退场。rollup_id=None＝全部取回。"""
        self._scache.clear()   # 条目增删：词面缓存整体失效
        arc = self._archive_load()
        if not arc:
            return {"restored": 0, "n_main": len(self.entries)}
        want: Optional[set] = None
        if rollup_id:
            r = self.entries.get(rollup_id)
            if not r or not r.get("rollup"):
                return {"restored": 0, "n_main": len(self.entries), "error": "rollup 不存在"}
            want = set((r.get("provenance") or [{}])[0].get("archived_ids") or [])
        kept, back = [], []
        for e in arc:
            (back if (want is None or e.get("id") in want) else kept).append(e)
        for e in back:
            if e["id"] in self.entries:          # 期间重入账过：合并不丢
                self.entries[e["id"]]["hits"] = int(self.entries[e["id"]].get("hits", 1)) + int(e.get("hits", 1))
            else:
                self.entries[e["id"]] = e
        if want is None:
            for rid in [k for k, v in self.entries.items() if v.get("rollup")]:
                self.entries.pop(rid, None)
        else:
            self.entries.pop(rollup_id, None)
        self._archive_save(kept)
        self.save()
        return {"restored": len(back), "n_main": len(self.entries),
                "n_archive": len(kept)}

    def replay(self, min_liveness: Optional[float] = None,
               limit: Optional[int] = None) -> List[dict]:
        """可回放（A2）：按时间序返回条目，供状态表重建。
        min_liveness: 只回放暖条目（冷条目留账本待同构复现唤醒；默认全量=旧行为）。
        limit: 只回放最近 N 条（默认全量）。两者叠加＝有界回放（init 成本上界）。"""
        items = sorted(self.entries.values(), key=lambda e: str(e.get("ts", "")))
        if min_liveness is not None:
            items = [e for e in items if float(e.get("liveness", 1.0)) >= min_liveness]
        if limit is not None and len(items) > limit:
            items = items[-limit:]
        return items

    def stats(self) -> dict:
        n = len(self.entries)
        lv = [float(e.get("liveness", 1.0)) for e in self.entries.values()]
        return {"n": n, "path": self.path,
                "liveness_min": min(lv) if lv else None,
                "liveness_max": max(lv) if lv else None,
                "bytes": os.path.getsize(self.path) if os.path.exists(self.path) else 0}
