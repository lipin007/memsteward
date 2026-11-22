#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""semantic_recall —— 混合计分 G∪E1 语义臂（MemGate 产品层，2026-11-12 落地）。

五病表 #3 修法落地：词面臂（calldecay.landing.recall，G）∪ 语义臂（本件，E1）。
全判证据（experiments/对照臂_20261112/full_verdict.json，可现场重算）：
G hit@3=41/78、E1=46/78、**并集 G∪E1=54/78**（互补 G-only 8／E1-only 13）。

分层：SDK（calldecay.landing）＝纯词面零改动；本件＝语义臂＋融合；
bridge_cli recall 与 daemon /decision（记忆体/daemon/serve.py）经 hybrid_recall
**同件组装**（fail-soft：语义臂任何故障→纯词面原样返回，零中断）——两个消费面
共享同一融合实现，防双面漂移。

口径：
- 候选面＝词面臂同款：转录类默认排除（include_transcripts＝显式审计面）；
  量门＝补丁①口径（decision 免 min_liveness，其余 ≥ min_liveness）。
- 短文档护栏 SEM_DOC_MIN=4（2026-11-13 存量清污拍板项②）：doc_text 去空白
  <4 字符不入语义候选面——≤3 字符 doc 的嵌入是噪声（'测 测'/'好 好' 对无关
  查询实测 cos 0.73 越过 SEM_FLOOR2 复活）；只滤语义面，词面臂不受影响，
  cb36 类真件长文档零波及。出处：experiments/存量清污_20261113/
  floor_pilot_result.json（face_short_docs=2、无关探针复活 3→1）＋REPORT.md §8；
  冻结集复算 E1 51→50（丢 qi47/58 退化自匹配、增 qi26）、union 54 不掉、
  产品面 18/43 不变。
- 放行下限 SEM_FLOOR=0.5（校准注记）：全判 E1 top-3 命中对 min cos=0.6646
  ⇒ 46/78 覆盖零损失；无关查询实测全拦（quantum banana 对 F4 夹具 0.29–0.33）。
- **第二判据 SEM_FLOOR2=0.70（semantic-only 严判，2026-11-13 缺口#4 修法）**：
  词面臂没有的条目（semantic-only）需 cos≥0.70；词面臂已有命中（G+E1 交织位）
  维持 SEM_FLOOR 宽判。校准出处：experiments/召回优化_20261112/floor2/
  calib_floor2.json（冻结集复算，锚=E1 46/G 41/并集 54 集合全等）：0.70 在
  并集硬约束紧上界 0.7104（E1-only 题 q0 最高 semantic-only rel cos）下取安全值，
  复算 E1 51/78（不降反升，清障抬位）＋并集 54/78 不掉；non-rel 对拦截率
  6/275→36/275。margin 族（top1−top2 门）实测掉并集 2-6 题——E1-only 题双真
  命中顶部天然拥挤（margin 0.005-0.03）与噪声（现在几点了 0.73/0.7297）同型
  不可分 ⇒ 弃用（不可兼得边界照登）。
  残留边界：同语种无关问句 max cos 可达 0.73（今天天气怎么样 0.7236/现在几点了
  0.73）仍过 0.70；要全拦需 floor2≥0.7303，会砍 E1-only 真命中（掉并集）——
  分数面不可分，精度靠词面臂 RECALL_GATE＋k 截断兜底（report_final.md 六原样）。
- 嵌入：nomic-embed v1.5 前缀（search_query: / search_document:）；条目侧向量
  内容寻址缓存 sidecar <landing>.emb.json（文本变→hash 变→自动失效；一次性
  摊销 449 条 5.1s，查询侧 ~4ms＋扫描 ~9ms/题）。
- 嵌入上游链（2026-11-13 缺口#3 修法）：MEMGATE_EMBED_URLS（逗号分隔声明序）
  → MEMGATE_EMBED_URL → 默认 8085；回落语义镜像 CallDecay proxy A25——仅传输
  失败（拒连/超时）与形状断言失败回落，合法响应即采用不按状态码猜；整调用钉
  一个上游防混嵌入空间；全挂 EmbedChainError→fail-soft 全等降级（同一出口）；
  EmbedCache 命中零网络（不变）。

保活：语义臂命中与词面臂同轨「被召回即保活」（五病 #2）：+0.1 封顶 1.0。
"""

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

QPFX = "search_query: "
DPFX = "search_document: "
SEM_FLOOR = 0.5
# 第二判据（缺口#4，semantic-only 严判）：词面臂没有的条目需 cos≥0.70。
# 出处：experiments/召回优化_20261112/floor2/calib_floor2.json（2026-11-13
# 冻结集复算，锚 E1 46/G 41/并集 54 集合全等）：0.70 位于并集硬约束紧上界
# 0.7104（E1-only 题最高 semantic-only rel cos）下的安全值；复算 E1 51/78、
# 并集 54/78 不掉、non-rel 拦截 6/275→36/275；margin 族实测掉并集已弃用。
SEM_FLOOR2 = 0.70
# 文档侧短文档护栏（存量清污 2026-11-13 拍板项②）：doc_text 去空白 <4 字符
# 的条目不入语义候选面（嵌入噪声，详见上方口径）。词面臂不受影响。
SEM_DOC_MIN = 4
DEFAULT_EMBED_URL = "http://127.0.0.1:8085/v1/embeddings"


def _sem_revive_mode():
    """语义复活模式旋钮（D2 立案 二.4，2026-11-13）：MEMGATE_SEM_REVIVE =
    revive（默认＝D2 保守档：冷命中只复活不注入）/ inject（D1 实验旋钮：冷命中当轮
    注入，只做旋钮不开默认）/ off（旧行为：量门剔冷，零复活）。
    运行时读 env（非 import 时快照）；未知值按默认 revive。"""
    v = (os.environ.get("MEMGATE_SEM_REVIVE") or "revive").strip().lower()
    if v in ("0", "off", "false", "no"):
        return "off"
    if v in ("inject", "d1"):
        return "inject"
    return "revive"


class EmbedChainError(RuntimeError):
    """嵌入上游链全挂（传输故障＋形状断言故障全数耗尽）。
    hybrid_recall 统一捕获走 fail-soft 全等降级（链路故障与语义臂故障同一出口）。"""


def resolve_embed_urls(explicit=None):
    """嵌入上游链解析（A25 多上游路由语义镜像，声明序即回落序）：
    explicit（调用方显式：单 URL / 逗号串 / URL 列表）→ $MEMGATE_EMBED_URLS
    （逗号分隔，声明序）→ $MEMGATE_EMBED_URL（单值）→ 默认 127.0.0.1:8085。
    运行时读 env（非 import 时快照）；返回非空 URL 列表。"""
    def split(v):
        if not v:
            return []
        parts = v.split(",") if isinstance(v, str) else list(v)
        return [u.strip() for u in parts if str(u).strip()]
    for cand in (split(explicit),
                 split(os.environ.get("MEMGATE_EMBED_URLS", "")),
                 split(os.environ.get("MEMGATE_EMBED_URL", ""))):
        if cand:
            return cand
    return [DEFAULT_EMBED_URL]


def _embed_batch_once(url, chunk, timeout):
    """单上游单批：返回向量表；可回落故障抛异常。
    回落语义（A25 镜像）：仅传输失败（拒连/超时）与形状断言失败可回落；
    上游返回合法响应（形状断言过）即采用——4xx/5xx 也是真实响应，不按状态码猜。"""
    req = urllib.request.Request(
        url, data=json.dumps({"input": chunk}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read() or b""  # 4xx/5xx 也是真实响应：形状过即采用，不按状态码回落
    d = json.loads(raw)        # 解析失败＝形状断言失败 → 抛 → 回落
    data = d.get("data")
    assert d.get("object") == "list" and isinstance(data, list) and \
        len(data) == len(chunk), \
        f"返回形状断言: data={len(data or [])}≠{len(chunk)}"
    emb = [x["embedding"] for x in data]
    dim = len(emb[0])
    assert dim > 0 and all(len(v) == dim for v in emb), "维度不齐"
    return emb


def embed_texts(urls, texts, batch=32, timeout=30):
    """批调嵌入服务（OpenAI 兼容 /v1/embeddings）＋双上游回落（缺口#3 修法）。
    urls: 单 URL / 逗号串 / URL 列表（声明序即回落序）；None → resolve_embed_urls()
    按 env 链解析。整调用钉一个上游（同批向量必须同嵌入空间，防混空间算余弦）；
    该上游任何一批传输/形状故障 → 整调用换下一上游重打（不半途换上游）。
    全链挂抛 EmbedChainError。缓存命中不经本函数（EmbedCache 在 semantic_topk
    层拦截，命中零网络）。
    返回形状断言（incidents #6）。"""
    chain = resolve_embed_urls(urls)
    errs = []
    for url in chain:
        try:
            vecs = []
            for i in range(0, len(texts), batch):
                chunk = texts[i:i + batch]
                vecs.extend(_embed_batch_once(url, chunk, timeout))
            return vecs
        except Exception as e:  # noqa: BLE001 —— 传输/形状故障皆回落下一个
            errs.append(f"{url}: {type(e).__name__}: {e}")
    raise EmbedChainError("嵌入上游链全挂: " + " | ".join(errs))


def _norm(v):
    s = sum(x * x for x in v) ** 0.5
    return [x / s for x in v] if s > 0 else list(v)


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


class EmbedCache:
    """内容寻址向量缓存（sha1(前缀+文本)→vec）：sidecar JSON 原子写（tmp+rename）。"""

    def __init__(self, path):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.vecs = json.load(f).get("vecs", {})
        except (OSError, ValueError):
            self.vecs = {}

    def get(self, key):
        return self.vecs.get(key)

    def put_many(self, pairs):
        self.vecs.update({k: [round(x, 5) for x in v] for k, v in pairs.items()})
        tmp = f"{self.path}.tmp.{os.getpid()}.{os.urandom(3).hex()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"vecs": self.vecs}, f)
        os.replace(tmp, self.path)


def _doc_text(e):
    from calldecay.landing import _recall_sig
    t = (_recall_sig(e) or "").strip()
    return t or " ".join(str(e.get(k, "")) for k in ("obj", "act", "actual", "cur"))


def _query_guarded(q):
    """W7 契约镜像（短拉丁护栏）：纯短拉丁查询不走语义臂——与词面臂前缀护栏
    同则（landing.py：两侧>=4 字符才比，短词护栏防 W5 式误命中）。含 CJK 或
    拉丁长 token（>=4 字符）的查询照常走语义臂。"""
    toks = [t for t in (q or "").replace("|", " ").replace("/", " ").split() if t]
    for t in toks:
        if any("\u4e00" <= ch <= "\u9fff" for ch in t) or len(t) >= 4:
            return False
    return True


def semantic_topk(store, query, k, embed_url=None, cache=None, floor=SEM_FLOOR,
                  min_liveness=0.03, include_transcripts=False,
                  include_quarantine=False, lex_ids=None, floor2=SEM_FLOOR2,
                  revived_out=None):
    """语义臂 top-k（只读打分；保活由调用方对合并结果统一做）。
    返回 [{"entry","score","liveness","class","arm":"E1","sem_cos"}] 降序（注入面）。
    候选面＝词面臂同款（转录默认排除＋补丁①量门口径）；查询面＝W7 短拉丁护栏。
    隔离条目（admit=quarantine，默认排除；五病#1）：include_quarantine=审计面。
    第二判据（缺口#4）：lex_ids（词面臂已命中条目集）内＝宽判 floor；
    semantic-only＝严判 max(floor, floor2)。floor2=None 关闭第二判据（纯旧语义，
    实验 A/B 用）；无 lex 信息时全部按 semantic-only 严判。

    语义复活 D2（MEMGATE_SEM_REVIVE，立案 二）：打分面放宽——非 decision、非转录类
    冷条目（liveness < min_liveness）也参与打分（decision 免量门=补丁① cls!="decision"
    别动；转录类照旧出面）。冷命中（is_cold 且 semantic-only 且 cos≥thr2）在
    revive 模式**只复活不注入**：不进返回行（本轮 hits），改经 revived_out 上报调用方
    去 keepalive(+0.1)；暖命中照旧注入。inject 模式冷命中当轮注入（D1 旋钮）。
    revived_out（可选 list）：收冷命中复活道 [{entry, sem_cos, liveness=lv_before}]，
    读打分不落盘；off 模式＝旧行为（量门剔冷、零复活、revived_out 留空）。"""
    from calldecay.landing import _entry_class
    from admission import is_quarantined

    mode = _sem_revive_mode()
    q = (query or "").strip()
    if not q or k <= 0 or _query_guarded(q):
        return []
    cands = []
    for e in store.entries.values():
        cls = _entry_class(e)
        if cls == "transcript" and not include_transcripts:
            continue
        if is_quarantined(e) and not (include_transcripts or include_quarantine):
            continue
        # 短文档护栏（SEM_DOC_MIN）：≤3 字符 doc 嵌入噪声不入语义面；词面臂不受影响。
        if len(_doc_text(e).strip()) < SEM_DOC_MIN:
            continue
        # 补丁①量门（cls!="decision" 别动）：off=旧行为（剔冷）；revive/inject=
        # 打分面放宽（非 decision 非转录类冷条目参与打分）。
        if mode == "off" and cls != "decision" \
                and float(e.get("liveness", 1.0)) < min_liveness:
            continue
        cands.append(e)
    if not cands:
        return []

    texts = {}
    keys = {}
    for e in cands:
        t = _doc_text(e)
        key = hashlib.sha1((DPFX + t).encode("utf-8")).hexdigest()
        keys[str(e.get("id"))] = key
        texts[key] = DPFX + t
    qkey = hashlib.sha1((QPFX + q).encode("utf-8")).hexdigest()

    vecs = {}
    if cache is not None:
        for key in [qkey] + list(keys.values()):
            v = cache.get(key)
            if v is not None:
                vecs[key] = v
    seen = set()
    miss_uniq = []
    for key in [qkey] + list(keys.values()):
        if key not in vecs and key not in seen:
            seen.add(key)
            miss_uniq.append(key)
    if miss_uniq:
        got = embed_texts(embed_url, [QPFX + q if key == qkey else texts[key]
                                      for key in miss_uniq])
        fresh = dict(zip(miss_uniq, got))
        vecs.update(fresh)
        if cache is not None:
            cache.put_many(fresh)
    qv = _norm(vecs[qkey])

    lex = {str(x) for x in (lex_ids or ())}
    thr2 = max(floor, floor2) if floor2 is not None else floor

    injectable = []   # (c, e)：本轮注入面候选
    cold_rev = []     # (c, e)：冷命中复活道（semantic-only 严判）
    for e in cands:
        eid = str(e.get("id"))
        v = vecs.get(keys[eid])
        if v is None:
            continue
        c = _cos(qv, _norm(v))
        cls = _entry_class(e)
        lv = float(e.get("liveness", 1.0))
        is_cold = cls != "decision" and cls != "transcript" and lv < min_liveness
        thr = floor if eid in lex else thr2
        passes = c >= thr
        cold_revive = is_cold and eid not in lex and c >= thr2
        if cold_revive:
            cold_rev.append((c, e))
        if mode == "off":
            # 旧行为：cands 已被量门剔冷，照旧注入阈值命中
            if passes:
                injectable.append((c, e))
        elif mode == "inject":
            # D1 旋钮：冷命中当轮注入（暖命中照旧）
            if passes and (not is_cold or cold_revive):
                injectable.append((c, e))
        else:  # revive：冷命中只复活不注入；暖命中照旧注入
            if passes and not is_cold:
                injectable.append((c, e))

    # 记忆分级加权（2026-11-17）：lesson(+0.20) > decision(+0.08) > chatter(0)。
    # 新条目用 memory_type 字段（入库时分级）；旧条目回退文本模式匹配。
    # 对齐业界：mem0 agent-fact 一等公民 / Letta core-archival 分层。
    LESSON_PATTERNS = ("教训", "铁律", "事故", "L01", "L02", "L03", "L04", "L05",
                       "L06", "L07", "L08", "L09", "L10", "L11", "L12", "L13", "L14",
                       "红线", "禁令", "不许", "禁止", "拍板", "根因", "预防")
    MED_PATTERNS = ("决策", "决议", "定案", "落定", "方案", "架构", "设计", "策略", "规矩")
    def _priority_bonus(e):
        # 优先用入库时分级的 memory_type
        mt = e.get("memory_type", "")
        if mt == "lesson":
            return 0.20
        if mt == "decision":
            return 0.08
        # 旧条目回退：文本模式匹配
        text = str(e.get("obj", "")) + str(e.get("act", "")) + str(e.get("actual", ""))
        for p in LESSON_PATTERNS:
            if p in text:
                return 0.20
        for p in MED_PATTERNS:
            if p in text:
                return 0.08
        return 0.0

    def _row(c, e):
        bonus = _priority_bonus(e)
        return {"entry": e, "score": round(c + bonus, 3),
                "liveness": float(e.get("liveness", 1.0)),
                "class": _entry_class(e), "arm": "E1", "sem_cos": round(c, 3),
                "priority_bonus": round(bonus, 3)}

    if revived_out is not None:
        revived_out.extend(_row(c, e) for c, e in cold_rev)
    injectable.sort(key=lambda t: (-t[0], str(t[1].get("ts", ""))))
    return [_row(c, e) for c, e in injectable[:k]]


def interleave(lex_hits, sem_hits, k):
    """G∪E1 交织去重（词面优先占位）：G1,S1,G2,S2,…截 k。
    k=6 时输出恰含两臂 top-3 并集——full_verdict 54/78 覆盖口径的实现形状。
    双臂同条目命中合并标注 arm=G+E1（观测口径，消费者仅用 entry/score）。"""
    out, seen = [], {}
    i = j = 0
    while len(out) < k and (i < len(lex_hits) or j < len(sem_hits)):
        for arm, lst in (("G", lex_hits), ("E1", sem_hits)):
            if len(out) >= k:
                break
            n = i if arm == "G" else j
            if n >= len(lst):
                continue
            h = lst[n]
            if arm == "G":
                i += 1
            else:
                j += 1
            eid = str(h.get("entry", {}).get("id"))
            if eid in seen:
                prev = seen[eid]
                if prev.get("arm") != arm:
                    prev["arm"] = "G+E1"
                    if "sem_cos" in h:
                        prev["sem_cos"] = h["sem_cos"]
                continue
            h = dict(h)
            h.setdefault("arm", arm)
            seen[eid] = h
            out.append(h)
    return out


def rerank(hits, query=""):
    """召回后重排序（2026-11-17，对齐 mem0 Multi-signal + Reranker）：
    五路融合：语义 score + memory_type + liveness + 时间 + BM25/实体加权。
    """
    import time as _time
    now = _time.time()
    # 实体索引（构建一次）
    eids = {str(h.get("entry", {}).get("id")) for h in hits}
    entries_map = {str(h.get("entry", {}).get("id")): h.get("entry", {}) for h in hits}
    entity_idx = build_entity_index(entries_map) if entries_map else {}
    bm25_scores = dict(bm25_score(query, entries_map)) if query else {}
    
    def _rerank_key(h):
        e = h.get("entry", {})
        eid = str(e.get("id", ""))
        base = float(h.get("score", 0))
        # 1. memory_type 加权
        mt = e.get("memory_type", "")
        type_bonus = {"lesson": 0.20, "decision": 0.08}.get(mt, 0.0)
        # 2. liveness 加权
        lv = float(e.get("liveness", 1.0))
        # 3. 时间衰减
        ts = e.get("ts", "")
        time_bonus = 0.0
        if ts:
            try:
                from datetime import datetime
                age_days = (now - datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").timestamp()) / 86400
                time_bonus = -0.05 if age_days > 30 else 0.0
            except (ValueError, OSError):
                pass
        # 4. 实体加权
        ent_bonus = entity_boost(query, {eid}, entity_idx) if query else 0.0
        # 5. BM25 加权（归一化到 0~0.10）
        bm25_bonus = min(0.10, bm25_scores.get(eid, 0) * 0.02) if query else 0.0
        return base + type_bonus + lv * 0.05 + time_bonus + ent_bonus + bm25_bonus
    return sorted(hits, key=_rerank_key, reverse=True)


def keepalive(store, hits, persist=True):
    """语义臂命中同轨保活（五病 #2 被召回即保活）：+0.1 封顶 1.0，写回命中行。
    persist=False：只动内存不落盘（daemon T0 只读口径，liveness 触碰零写回）。"""
    from calldecay.landing import _lv_set_quiet
    bumped = {}
    for h in hits:
        e = h.get("entry")
        if not isinstance(e, dict):
            continue
        nv = min(1.0, float(e.get("liveness", 1.0)) + 0.1)
        _lv_set_quiet(e, nv)
        h["liveness"] = nv
        bumped[str(e.get("id"))] = nv
    if bumped and persist:
        store._persist_liveness(bumped)


def hybrid_recall(store, lex_hits, query, k, cache_path=None, embed_url=None,
                  floor=SEM_FLOOR, min_liveness=0.03, include_transcripts=False,
                  include_quarantine=False, persist=True, floor2=SEM_FLOOR2,
                  revived_out=None):
    """G∪E1 混合计分装配（单源件）：语义臂 top-k ∪ 词面臂交织去重＋语义命中
    同轨保活。bridge_cli recall 与 daemon /decision 共用本件——两个消费面共享
    同一融合实现，防双面漂移。

    全 fail-soft：语义臂任何故障（嵌入服务死/缓存写失败/形状断言）→ 原样返回
    lex_hits（全等降级，零中断）。关闭开关：MEMGATE_HYBRID=0（env；调用方另有
    --no-hybrid 旗标时在调用侧短路）。
    persist=False：保活只动内存不落盘（daemon T0 只读口径）。

    语义复活 D2（立案 二）：revive 模式下冷命中（semantic-only 严判）只复活不注入
    ——keepalive(+0.1) 落盘、不进本轮 hits；暖命中照旧注入＋保活。inject 模式冷命中
    当轮注入（D1 旋钮）。revived_out（可选 list）：收复活记录
    [{id, sem_cos, lv_before, lv_after}]（信封 additive，既有键不动）。"""
    if os.environ.get("MEMGATE_HYBRID", "1").strip().lower() \
            in ("0", "off", "false", "no"):
        return lex_hits
    try:
        mode = _sem_revive_mode()
        cache = EmbedCache(cache_path) if cache_path else None
        lex_ids = {str(h.get("entry", {}).get("id")) for h in lex_hits}
        cold = []   # 冷命中复活道（semantic-only 严判，来自 semantic_topk）
        sem = semantic_topk(store, query, k, embed_url=embed_url, cache=cache,
                            floor=floor, min_liveness=min_liveness,
                            include_transcripts=include_transcripts,
                            include_quarantine=include_quarantine,
                            lex_ids=lex_ids, floor2=floor2, revived_out=cold)
        # 记 lv_before（复活 +0.1 前）；冷命中在 inject 模式已进 sem，随暖命中保活，
        # revive 模式不进 sem 需补保活——两路不叠加（防双保活）。
        for h in cold:
            h["_lv_before"] = float(h.get("entry", {}).get("liveness", 1.0))
        keep = [h for h in sem
                if str(h.get("entry", {}).get("id")) not in lex_ids]
        if mode == "revive":
            keep = keep + cold
        keepalive(store, keep, persist=persist)
        revived = [{"id": str(h.get("entry", {}).get("id")),
                    "sem_cos": h.get("sem_cos"),
                    "lv_before": h.get("_lv_before"),
                    "lv_after": round(float(h.get("entry", {}).get("liveness", 1.0)), 4)}
                   for h in cold]
        if revived_out is not None:
            revived_out.extend(revived)
        return rerank(interleave(lex_hits, sem, k))
    except Exception as e:  # noqa: BLE001 —— 语义臂故障不阻断召回
        print(f"[memgate] 语义臂不可用（fail-soft 纯词面）: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return lex_hits


# ── 实体链接（2026-11-17，对齐 mem0 Entity Boost）────────────────
# 解决「搜『进程』找不到 pkill 教训」问题：从教训/铁律中提取关键词，
# 建立实体→条目索引，检索时实体命中即加权。

_ENTITY_STOPWORDS = set("的了在是我你他她它们这那就都也很还只不没会能可以对和与或被把让给向从到过上下前后左右".split())

def extract_entities(text: str) -> set:
    """从文本提取实体关键词（2026-11-17 优化：中文 2-3 字短词拆分）
    修复：『不查仓就动手』→ {不查, 查仓, 仓就, 就动, 动手} 而非整句一个实体"""
    import re
    entities = set()
    # 英文标识符（pkill, git, commit, L01 等）
    for m in re.finditer(r'[a-zA-Z_][a-zA-Z0-9_]{2,}', text):
        entities.add(m.group().lower())
    # 编号（L01-L14）
    for m in re.finditer(r'L\d{2}', text):
        entities.add(m.group())
    # 中文关键词：2-3 字短词（拆开更精准匹配）
    for m in re.finditer(r'[一-鿿]{2,}', text):
        s = m.group()
        if len(s) <= 3:
            if s not in _ENTITY_STOPWORDS:
                entities.add(s)
        else:
            # 长串拆 2-3 字滑窗
            for i in range(len(s) - 1):
                bigram = s[i:i+2]
                if bigram not in _ENTITY_STOPWORDS:
                    entities.add(bigram)
                if i + 3 <= len(s):
                    trigram = s[i:i+3]
                    if trigram not in _ENTITY_STOPWORDS:
                        entities.add(trigram)
    return entities


def build_entity_index(entries: dict) -> dict:
    """构建实体→条目ID倒排索引"""
    index = {}  # entity -> set(entry_id)
    for eid, e in entries.items():
        text = f"{e.get('obj','')} {e.get('act','')} {e.get('actual','')}"
        for ent in extract_entities(text):
            index.setdefault(ent, set()).add(str(eid))
    return index


def entity_boost(query: str, entry_ids: set, entity_index: dict) -> float:
    """查询与条目的实体重叠度加成：0~0.12"""
    q_ents = extract_entities(query)
    if not q_ents:
        return 0.0
    overlap = sum(1 for e in q_ents if e in entity_index and entry_ids & entity_index[e])
    return min(0.12, overlap * 0.04)


# ── BM25 关键词检索（2026-11-17，对齐 mem0 Multi-signal）────────
# 弥补语义盲区：精确关键词（pkill, L02, git status）语义嵌入可能匹配不到，
# BM25 词面精确匹配可以补上。

def _cjk_bigrams(text: str) -> set:
    """中文 2-gram 重叠切分：『不查仓就动手』→ {不查,查仓,仓就,就动,动手}
    解决整句当一个 token 导致零匹配的问题。"""
    import re
    tokens = set()
    # 英文标识符整取
    for m in re.finditer(r'[a-zA-Z_][a-zA-Z0-9_]{1,}', text):
        tokens.add(m.group().lower())
    # 中文串按 2-gram 重叠切
    for m in re.finditer(r'[一-鿿]{2,}', text):
        s = m.group()
        if len(s) == 2:
            tokens.add(s)
        else:
            for i in range(len(s) - 1):
                tokens.add(s[i:i+2])
    return tokens


def bm25_score(query: str, entries: dict, k1: float = 1.5, b: float = 0.75) -> list:
    """简化 BM25：返回 [(score, entry_id)] 降序"""
    import math, re
    def _tokens(s):
        return _cjk_bigrams(s)
    
    q_tokens = _tokens(query)
    if not q_tokens:
        return []
    
    # 文档频率
    n = len(entries)
    doc_tokens = {}
    df = {}
    for eid, e in entries.items():
        text = f"{e.get('obj','')} {e.get('act','')} {e.get('actual','')}"
        toks = _tokens(text)
        doc_tokens[str(eid)] = toks
        for t in toks:
            df[t] = df.get(t, 0) + 1
    
    avg_dl = sum(len(v) for v in doc_tokens.values()) / max(n, 1)
    results = []
    for eid, toks in doc_tokens.items():
        score = 0.0
        for qt in q_tokens:
            if qt not in toks:
                continue
            tf = 1  # binary tf for simplicity
            idf = math.log((n - df.get(qt, 0) + 0.5) / (df.get(qt, 0) + 0.5) + 1)
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * len(toks) / avg_dl))
        if score > 0:
            results.append((score, eid))
    return sorted(results, reverse=True)


# ── 记忆蒸馏（2026-11-17，对齐 Letta 自主遗忘）────────────────
# 定期把海量条目提炼成精华教训，减少噪声干扰。

def distill_memories(entries: dict, top_n: int = 50) -> list:
    """蒸馏精华：从海量条目中挑出最高价值的教训/决策。
    优先级：lesson > decision > 高 hits > 高 liveness
    返回 [{entry_id, memory_type, text, score}]"""
    candidates = []
    for eid, e in entries.items():
        mt = e.get("memory_type", "")
        if mt not in ("lesson", "decision"):
            continue
        score = {
            "lesson": 3.0,
            "decision": 1.5,
        }.get(mt, 0.0)
        score += int(e.get("hits", 1)) * 0.3
        score += float(e.get("liveness", 1.0)) * 0.5
        text = f"{e.get('obj','')} {e.get('act','')} {e.get('actual','')}"
        candidates.append({
            "entry_id": str(eid), "memory_type": mt,
            "text": text[:200], "score": round(score, 2)
        })
    return sorted(candidates, key=lambda x: x["score"], reverse=True)[:top_n]


def get_essential_lessons(entries: dict, top_n: int = 20) -> str:
    """输出精华教训清单（可直接注入 system prompt）"""
    distilled = distill_memories(entries, top_n)
    if not distilled:
        return ""
    lines = ["## 精华教训（蒸馏自长期记忆）"]
    for i, d in enumerate(distilled, 1):
        tag = "🔴" if d["memory_type"] == "lesson" else "🟡"
        lines.append(f"{i}. {tag} {d['text'][:100]}")
    return "\n".join(lines)
