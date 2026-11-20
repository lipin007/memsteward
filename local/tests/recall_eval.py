#!/usr/bin/env python3
"""recall_eval.py — 召回质量评估（2026-11-17，对齐 Zep eval-harness）

测试集：已知的「教训→应召回」配对，测召回命中率。
指标：
  hit_rate    = 命中数 / 查询数（教训出现在 top-k）
  lesson_rank = 教训的平均排名（越小越好）
  mrr         = 平均倒数排名（1/rank 的均值，越大越好）
"""
import json, urllib.request, sys

DAEMON = "http://127.0.0.1:8877/decision"

def query_daemon(signature, k=6):
    data = json.dumps({"session": "eval", "signature": signature, "k": k,
                        "messages": [], "total_messages": 0}).encode()
    req = urllib.request.Request(DAEMON, data=data,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)

# 测试集：查询 → 应该召回的教训关键词
TEST_CASES = [
    ("不查仓就动手", ["查仓", "不查仓", "重复造轮子"]),
    ("进程收尾", ["pkill", "pgrep", "pid"]),
    ("记忆文件写入", ["覆盖", "追加", "cat >>"]),
    ("提交代码", ["git add", "git status", "fail-fast"]),
    ("验证", ["fail-fast", "verify", "对照"]),
]

def evaluate():
    hits = 0
    ranks = []
    mrr_sum = 0.0
    for query, expected_keywords in TEST_CASES:
        result = query_daemon(query, k=6)
        entries = [h.get("entry", {}) for h in result.get("hits", [])]
        # 找期望关键词在结果中的排名
        found_rank = None
        for i, e in enumerate(entries):
            text = json.dumps(e, ensure_ascii=False)
            if any(kw in text for kw in expected_keywords):
                found_rank = i + 1
                break
        if found_rank:
            hits += 1
            ranks.append(found_rank)
            mrr_sum += 1.0 / found_rank
            print(f"  ✅ '{query}' → rank {found_rank}")
        else:
            ranks.append(999)
            print(f"  ❌ '{query}' → 未命中")
    
    n = len(TEST_CASES)
    hit_rate = hits / n
    avg_rank = sum(r for r in ranks if r < 999) / max(hits, 1)
    mrr = mrr_sum / n
    
    print(f"\n=== 召回质量 ===")
    print(f"  hit_rate:  {hit_rate:.1%} ({hits}/{n})")
    print(f"  avg_rank:  {avg_rank:.1f} (教训平均排名)")
    print(f"  MRR:       {mrr:.3f} (1=完美, 0=全丢)")
    return {"hit_rate": hit_rate, "avg_rank": avg_rank, "mrr": mrr}

if __name__ == "__main__":
    evaluate()
