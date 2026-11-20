"""
KnowledgeDistiller — 通用知识蒸馏器

原始数据（日志/传感器/事件流）→ 结构化知识（edge/goal/block）。
不依赖特定游戏格式，接受通用 dict 输入。

通用输入格式：
  observations: [{"pos": (x,y), "action": a, "before": {...}, "after": {...}}, ...]
  或 {"edges": {...}, "targets": [...], "changers": [...]}  # 已有图结构
"""

import re


class KnowledgeDistiller:
    @staticmethod
    def distill_from_text(text, max_knowledge=2):
        """从文本提取结构化知识。通用格式。
        
        提取: 决策/教训/事实/模式
        """
        knowledge = []
        if not text or len(text.strip()) < 8:
            return knowledge
        text = text.strip()
        import re
        if re.search(r'lesson|mistake|error|always|never|remember', text, re.I) or any(k in text for k in ['教训','不要','禁止','必须','记住']):
            knowledge.append({'type': 'lesson', 'knowledge': text[:300], 'confidence': 0.8})
        if any(k in text for k in ['决定','选择','拍板','采用','选用']) or re.search(r'decide|choose', text, re.I):
            knowledge.append({'type': 'decision', 'knowledge': text[:300], 'confidence': 0.7})
        if re.search(r'\d+\.\d+|x=|y=', text):
            knowledge.append({'type': 'fact', 'knowledge': text[:300], 'confidence': 0.6})
        knowledge.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        return knowledge[:max_knowledge]

    @staticmethod
    def distill_from_graph(edges=None, targets=None, changers=None):
        """从图结构提取路线知识。通用格式。"""
        knowledge = {"edges": [], "goals": [], "blocks": []}

        for key, val in (edges or {}).items():
            if "|" not in key:
                continue
            pos_str, action_str = key.split("|", 1)
            try:
                x, y = map(int, pos_str.split(","))
                a = int(action_str)
            except ValueError:
                continue
            if val == "blocked":
                knowledge["blocks"].append({"from": (x, y), "action": a, "type": "blocked"})
            else:
                try:
                    tx, ty = map(int, val.split(","))
                    knowledge["edges"].append({"from": (x, y), "action": a, "to": (tx, ty), "type": "edge"})
                except ValueError:
                    continue

        for t in (targets or []):
            parsed = KnowledgeDistiller._parse_coord(t)
            if parsed:
                knowledge["goals"].append({"pos": parsed, "kind": "target"})

        for c in (changers or []):
            parsed = KnowledgeDistiller._parse_coord(c)
            if parsed:
                knowledge["goals"].append({"pos": parsed, "kind": "changer"})

        return knowledge

    @staticmethod
    def distill_from_observations(entries):
        """从观察条目提取路线知识。通用日志解析。"""
        knowledge = {"edges": [], "goals": [], "blocks": []}
        for e in entries:
            obj = e.get("obj", "")
            actual = e.get("actual", "")
            m = re.match(r'change@\((\d+),\s*(\d+)\)', obj)
            if not m:
                continue
            pos = (int(m.group(1)), int(m.group(2)))
            if "new_target" in actual or "target" in actual.lower():
                tm = re.search(r'(?:target|new_target)[:(\(]*(\d+),\s*(\d+)', actual)
                if tm:
                    knowledge["goals"].append({
                        "pos": (int(tm.group(1)), int(tm.group(2))),
                        "kind": "target", "source": f"observed@{pos}"})
            elif "blocked" in actual.lower():
                knowledge["blocks"].append({
                    "from": pos, "action": e.get("act", ""),
                    "type": "blocked", "source": "observed"})
        return knowledge

    @staticmethod
    def to_prior_format(knowledge):
        entries = []
        for e in knowledge.get("edges", []):
            entries.append({
                "obj": f"edge:{e['from'][0]},{e['from'][1]}",
                "act": f"action{e['action']}",
                "actual": f"to:{e['to'][0]},{e['to'][1]}",
                "kind": "prior"})
        for g in knowledge.get("goals", []):
            entries.append({
                "obj": f"{g['kind']}:{g['pos'][0]},{g['pos'][1]}",
                "act": "location",
                "actual": f"at:{g['pos'][0]},{g['pos'][1]}",
                "kind": "prior"})
        for b in knowledge.get("blocks", []):
            entries.append({
                "obj": f"block:{b['from'][0]},{b['from'][1]}",
                "act": f"action{b['action']}",
                "actual": "blocked",
                "kind": "prior"})
        return {"entries": entries}

    @staticmethod
    def _parse_coord(item):
        if isinstance(item, (list, tuple)) and len(item) == 2:
            try:
                return (int(item[0]), int(item[1]))
            except (ValueError, TypeError):
                pass
        if isinstance(item, str):
            parts = item.split(",")
            if len(parts) == 2:
                try:
                    return (int(parts[0].strip()), int(parts[1].strip()))
                except ValueError:
                    pass
        return None

    @staticmethod
    def summarize(knowledge):
        return {
            "edges": len(knowledge.get("edges", [])),
            "goals": len(knowledge.get("goals", [])),
            "blocks": len(knowledge.get("blocks", [])),
        }


    @staticmethod
    def deduplicate(knowledge_list, similarity_threshold=0.7):
        """语义去重: 相似知识只保留一条"""
        import re
        seen = []
        unique = []
        for k in knowledge_list:
            is_dup = False
            for s in seen:
                # 简单词重叠度 (生产环境用 embedding)
                k_str = k.get('knowledge', '')
                s_str = s.get('knowledge', '')
                # 字符级 2-gram 去重 (中文友好)
                k_bigrams = set(k_str[i:i+2] for i in range(len(k_str)-1))
                s_bigrams = set(s_str[i:i+2] for i in range(len(s_str)-1))
                if k_bigrams and s_bigrams:
                    overlap = len(k_bigrams & s_bigrams) / max(len(k_bigrams), len(s_bigrams))
                    if overlap > similarity_threshold:
                        is_dup = True
                        break
            if not is_dup:
                seen.append(k)
                unique.append(k)
        return unique

    @staticmethod
    def filter_by_confidence(knowledge_list, min_confidence=0.5):
        """置信度过滤: 低置信度不存"""
        return [k for k in knowledge_list if k.get('confidence', 0) >= min_confidence]

    @staticmethod
    def batch_distill(texts, llm_fn=None):
        """批量蒸馏: 多段文本 → 提取 → 去重 → 过滤
        
        llm_fn: 可选 LLM 提取函数 (prompt) -> str
        如果没有 llm_fn, 用关键词规则
        """
        all_knowledge = []
        for text in texts:
            if llm_fn:
                # LLM 提取 (竞品方法)
                try:
                    prompt = f"Extract key facts, lessons, and decisions from: {text[:500]}"
                    result = llm_fn(prompt)
                    if result:
                        all_knowledge.append({'type': 'llm_extract', 'knowledge': result, 'confidence': 0.9})
                except:
                    pass
            # 规则提取 (兜底)
            all_knowledge.extend(KnowledgeDistiller.distill_from_text(text))
        
        # 去重 + 过滤
        all_knowledge = KnowledgeDistiller.deduplicate(all_knowledge)
        all_knowledge = KnowledgeDistiller.filter_by_confidence(all_knowledge)
        return all_knowledge
