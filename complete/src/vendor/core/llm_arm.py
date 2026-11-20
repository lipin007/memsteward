"""LLM 决策臂: 概念空间精疲力尽时的外部候选 (路线 3, 2026-09-24)

黄金准则:
- LLM 臂 = 第一候选, 不是最终决策者 — 候选最终由元仲裁/轮换决定
- LLM 候选不设预期 (与记忆候选同级, 结果由 RPE 自然修正)
- gated 默认关 (LLM_ARM=1 启用) — 零影响既有行为
- 所有 LLM 调用审计日志 → experiments/llm_arm/audit/ (可复现)
- 超时 fallback → None (不阻塞行为环)
- 调用方: decision_symbolic.decide_symbolic 在 unplanned 回退路径中
- 后端: llama.cpp server (OpenAI 兼容 API), 本机 8082 端口

三铁律:
  1. LLM 臂不写 concept_space, 不调边权重, 不提建议 — 只建议动作
  2. 所有建议标注 is_explore=True (不设预期)
  3. 默认关已验证 (全量回归时 LLM_ARM=0 逐位不变)
"""
import json
import logging
import os
import subprocess
import time
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List

log = logging.getLogger(__name__)

# ── gated ────────────────────────────────────────────────
ENABLED = os.environ.get('LLM_ARM', '0') == '1'
_AUDIT_DIR = os.environ.get('LLM_ARM_AUDIT_DIR',
                            'experiments/llm_arm/audit/')

# 后端: llama.cpp server (OpenAI 兼容)；LLM_ARM_HOSTS=逗号分隔回落链（首项优先，
# 2026-11-06 包裹本地模型模式：本地模型 + 云 API 组合），未设则等价单主机旧行为。
_LLAMA_HOST = os.environ.get('LLM_ARM_HOST', 'http://localhost:8082')
_HOSTS_RAW = os.environ.get('LLM_ARM_HOSTS', '') or _LLAMA_HOST
_LLAMA_HOSTS = [h.strip() for h in _HOSTS_RAW.split(',') if h.strip()]
_TIMEOUT = int(os.environ.get('LLM_ARM_TIMEOUT', '15'))

# ── 门控降级逻辑 ────────────────────────────────────────
# 门控等级 0-4 (BAN/OFF/RELUCTANT/NORMAL/EAGER)
_GATE_LEVEL = int(os.environ.get('LLM_ARM_GATE', '0'))  # 默认 OFF
_GATE_LEVEL_DEFAULT = _GATE_LEVEL

# 调用概率映射 (level -> probability)
_GATE_PROB_MAP = {0: 0.0, 1: 0.0, 2: 0.1, 3: 0.5, 4: 0.9}

# 评估窗口
_GATE_EVAL_L = int(os.environ.get('LLM_ARM_EVAL_L', '10'))
_GATE_FAIL_N = int(os.environ.get('LLM_ARM_FAIL_N', '5'))

# 调用历史 (列表, 每条 {'action_ok': bool, 'novelty_resolved': bool})
_gate_history: list = []

# ======== 门控 API ========
def gate_level() -> int:
    return _GATE_LEVEL

def gate_level_str(level: int = _GATE_LEVEL) -> str:
    return ['BAN', 'OFF', 'RELUCTANT', 'NORMAL', 'EAGER'][min(level, 4)]

def gate_should_call() -> bool:
    """根据当前门控等级和调用概率决定是否调 LLM"""
    if _QUARANTINE['active']:
        return gate_quarantine_probe_due()   # 隔离期: 仅探测调用可出
    if _GATE_LEVEL == 0 or _GATE_LEVEL == 1:
        return False
    p = _GATE_PROB_MAP.get(_GATE_LEVEL, 0.0)
    import random
    return random.random() < p

def gate_raise(novelty_strength: float = 0.0):
    """提升门控等级.
    Args:
        novelty_strength: 新颖性增益(>2.0 直接跃升到 3)
    """
    global _GATE_LEVEL
    if novelty_strength > 2.0:
        _GATE_LEVEL = max(_GATE_LEVEL, 3)  # 直接跃升到 NORMAL
    else:
        _GATE_LEVEL = min(_GATE_LEVEL + 1, 4)

def gate_record_call(action_ok: bool, novelty_resolved: bool):
    """记录一次 LLM 调用结果, 用于降级评估"""
    _gate_history.append({'action_ok': action_ok, 'novelty_resolved': novelty_resolved})
    # 截断历史到评估窗口大小
    while len(_gate_history) > _GATE_EVAL_L + 5:
        _gate_history.pop(0)

def gate_eval_downgrade() -> bool:
    """评估最近 L 条调用, 若条件满足则降级. 返回 True = 已降级"""
    global _GATE_LEVEL
    if _GATE_LEVEL <= 1:
        return False
    recent = _gate_history[-_GATE_EVAL_L:] if len(_gate_history) >= _GATE_EVAL_L else _gate_history
    if len(recent) < _GATE_EVAL_L // 2:
        return False  # 样本不足, 不评估
    # 有效动作率
    n_ok = sum(1 for r in recent if r['action_ok'])
    n_resolved = sum(1 for r in recent if r['novelty_resolved'])
    # 降级条件: 有效动作率 > 0.8 且新颖性已消退
    if n_ok >= len(recent) * 0.8 and n_resolved >= len(recent) * 0.8:
        _GATE_LEVEL = max(_GATE_LEVEL - 1, 1)
        return True
    return False

# ── 门控隔离 (对称信任规则: 有效动作率下限隔离 + 探测恢复) ──
# 2026-09-27: 补"顾问失效不切断"缺口. 默认关 (LLM_ARM_QUARANTINE=0) ⇒ 零行为变化.
# 触发: 滑窗 _QUAR_W 条调用的有效动作率 < _QUAR_LOW ⇒ 隔离 (仅探测可出)
# 解除: 探测连续 _QUAR_PROBE_N 次有效率 ≥ _QUAR_HIGH ⇒ 恢复 (对称峰值保持)
_QUAR_ENABLED = os.environ.get('LLM_ARM_QUARANTINE', '0') == '1'
_QUAR_LOW = float(os.environ.get('LLM_ARM_QUAR_LOW', '0.2'))
_QUAR_HIGH = float(os.environ.get('LLM_ARM_QUAR_HIGH', '0.5'))
_QUAR_W = int(os.environ.get('LLM_ARM_QUAR_W', '10'))
_QUAR_K = int(os.environ.get('LLM_ARM_QUAR_K', '5'))
_QUAR_PROBE_N = int(os.environ.get('LLM_ARM_QUAR_PROBE_N', '3'))
_QUARANTINE = {'active': False, 'enter_step': None, 'steps_since_probe': 0,
               'probe_results': [], 'events': []}


def gate_quarantine_active() -> bool:
    return _QUARANTINE['active']


def gate_eval_quarantine(step: int = 0) -> str:
    """每步调用. 返回 'none' | 'enter'. 新颖性不解除隔离 (仅探测可解除)"""
    if not _QUAR_ENABLED:
        return 'none'
    q = _QUARANTINE
    if q['active']:
        q['steps_since_probe'] += 1
        return 'none'
    recent = _gate_history[-_QUAR_W:] if len(_gate_history) >= _QUAR_W else _gate_history
    if len(recent) >= max(_QUAR_W // 2, 2):
        rate = sum(1 for r in recent if r['action_ok']) / len(recent)
        if rate < _QUAR_LOW:
            q.update(active=True, enter_step=step, steps_since_probe=0, probe_results=[])
            q['events'].append({'type': 'enter', 'step': step, 'rate': round(rate, 3)})
            return 'enter'
    return 'none'


def gate_quarantine_probe_due() -> bool:
    q = _QUARANTINE
    return q['active'] and q['steps_since_probe'] >= _QUAR_K


def gate_quarantine_record_probe(action_ok: bool, step: int = 0) -> str:
    """探测结果记录; 连续 _QUAR_PROBE_N 次有效率 ≥ _QUAR_HIGH ⇒ 解除隔离"""
    q = _QUARANTINE
    q['steps_since_probe'] = 0
    q['probe_results'].append(bool(action_ok))
    if len(q['probe_results']) >= _QUAR_PROBE_N:
        rate = sum(q['probe_results']) / len(q['probe_results'])
        if rate >= _QUAR_HIGH:
            q.update(active=False, probe_results=[])
            q['events'].append({'type': 'exit', 'step': step, 'rate': round(rate, 3)})
            return 'exit'
    return 'stay'


def gate_quarantine_state() -> dict:
    q = _QUARANTINE
    return {'active': q['active'], 'enter_step': q['enter_step'],
            'steps_since_probe': q['steps_since_probe'],
            'probe_results': list(q['probe_results']), 'events': list(q['events']),
            'enabled': _QUAR_ENABLED, 'low': _QUAR_LOW, 'high': _QUAR_HIGH,
            'window': _QUAR_W, 'probe_interval': _QUAR_K,
            'probe_n': _QUAR_PROBE_N}


def gate_reset():
    """重置门控到默认 (LLM_ARM=1 启动时的初始等级)"""
    global _GATE_LEVEL
    global _gate_history
    _GATE_LEVEL = int(os.environ.get('LLM_ARM_GATE', '0'))
    _gate_history = []
    _QUARANTINE.update(active=False, enter_step=None, steps_since_probe=0,
                       probe_results=[], events=[])

def gate_full_state() -> dict:
    return {
        'level': _GATE_LEVEL,
        'label': gate_level_str(),
        'call_prob': _GATE_PROB_MAP.get(_GATE_LEVEL, 0.0),
        'history_len': len(_gate_history),
        'eval_window': _GATE_EVAL_L,
    }


# ── 审计 ──────────────────────────────────────────────────
def _audit_log(entry: dict):
    """每一条 LLM 调用记录审计文件 (JSONL)"""
    if not ENABLED:
        return
    try:
        os.makedirs(_AUDIT_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        path = os.path.join(_AUDIT_DIR, f'llm_arm_{ts}.json')
        with open(path, 'w') as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"[LLM] audit write failed: {e}")


def _health(host: str = _LLAMA_HOST) -> dict:
    """llama.cpp server 健康检查"""
    try:
        r = subprocess.run(
            ['curl', '-s', f'{host}/health'],
            capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return {'ok': False, 'error': f'curl failed: {r.stderr[:200]}'}
        data = json.loads(r.stdout)
        return {'ok': data.get('status') == 'ok',
                'detail': r.stdout[:200]}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ── accept 契约 + 候选准入 (F1/F3): 公共契约模块, 单一来源 (B4) ──
# 见 core/accept_contract.py — 治理层/记忆层两层共享同一 accept 契约,
try:
    from core.accept_contract import accept, admit   # noqa: E402
except ImportError:
    from accept_contract import accept, admit       # noqa: E402


# ── 核心建议函数 ───────────────────────────────────────────
def suggest(obj: str, goal: str, current: Optional[str] = None,
            world_name: str = '',
            actions: Optional[List[str]] = None,
            context: Optional[List] = None,
            timeline: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """当离散符号层无解时, 问外部 LLM 获得候选动作.

    Args:
        obj: 当前操作对象
        goal: 目标状态
        current: 当前状态
        world_name: 世界名 (用于 prompt 上下文)
        actions: 可用动作列表
        context: 关联对象状态 (context of SymbolicDecision)
        timeline: 近期事件流 (最后 5-10 条)

    Returns:
        {'act': str, 'confidence': float, 'reasoning': str}
        None = 无候选 (超时/失败/关闭)
    """
    if not ENABLED:
        return None

    # 门控检查: 根据等级和概率决定是否调 LLM
    if not gate_should_call():
        return None

    # 健康检查
    health = _health()
    if not health['ok']:
        log.warning(f"[LLM] llama.cpp unreachable: {health.get('error')}")
        return None

    # --- 构建 prompt ---
    prompt_lines: List[str] = [
        "You are a decision assistant for an autonomous agent.",
        "",
        f"You are in world '{world_name}'.",
        f"Current object: {obj}",
    ]
    if current:
        prompt_lines.append(f"Current state: {current}")
    if goal:
        prompt_lines.append(f"Goal: {goal}")
    else:
        prompt_lines.append("Goal: maximize reward (no specific target state)")

    if actions:
        prompt_lines.append(f"Available actions: {', '.join(actions)}")

    if context:
        ctx_str = '; '.join([f"{k}={v}" for k, v in context[:6]])
        prompt_lines.append(f"Context: {ctx_str}")

    if timeline:
        last_events = timeline[-8:]
        prompt_lines.append("Recent events:")
        for ev in last_events:
            prompt_lines.append(f"  - {ev}")

    # 状态感知提示: 当前状态过度时引导保守动作
    # LLM_ARM_HINTS=0 = 消融开关 (提示行编码 2/3 评分分支, 归因实验需关提示)
    if current and os.environ.get('LLM_ARM_HINTS', '1') != '0':
        if current in ('暴增', '爆炸', '多', '过多'):
            prompt_lines.append("")
            prompt_lines.append("提示: 当前状态已接近/超过目标,优先选择观望或放牧")
        elif current in ('濒危', '危险', '即将灭绝'):
            prompt_lines.append("")
            prompt_lines.append("提示: 当前状态极端低落,优先选择保护")

    prompt_lines.append("")
    prompt_lines.append("最佳:")

    prompt = '\n'.join(prompt_lines)

    # --- 调用 llama.cpp API (OpenAI 兼容) ---
    _use_chat = os.environ.get('LLM_ARM_CHAT', '0') == '1'
    if _use_chat:
        # gemma 系 raw 续写不兼容 (回显提示行/裸数字/控制符泄漏, 2026-09-27 审计实锤),
        # 走模型原生 chat 端点; 默认路径零变化
        payload = json.dumps({
            'model': os.environ.get('LLM_ARM_MODEL', ''),
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.0,
            'max_tokens': 512,
        })
    else:
        payload = json.dumps({
            'prompt': prompt,
            'n_predict': 4,
            'temperature': 0.0,
            'stop': ['```', '###', '\n', '。', '.'],
            'cache_prompt': True,  # KV cache 复用: 相同前缀只算一次 (2026-11-18)
        })

    entry: Dict[str, Any] = {
        'timestamp': datetime.now().isoformat(),
        'prompt_snippet': prompt[:300],
        'world': world_name,
        'obj': obj,
        'goal': goal,
        'current': current,
        'actions': actions,
    }

    start = time.time()
    try:
        # 主机链回落（2026-11-06）：传输失败（拒连/curl 非 0/超时）换下家；
        # 单主机时行为与旧版一致。
        r = None
        _tried = []
        for _host in _LLAMA_HOSTS:
            _api_url = (f'{_host}/v1/chat/completions' if _use_chat
                        else f'{_host}/completion')
            try:
                r = subprocess.run(
                    ['curl', '-s', '-X', 'POST',
                     _api_url,
                     '-d', payload],
                    capture_output=True, text=True, timeout=_TIMEOUT)
            except subprocess.TimeoutExpired:
                _tried.append(f'{_host}(timeout)')
                r = None
                continue
            if r.returncode != 0:
                _tried.append(f'{_host}(curl {r.returncode})')
                r = None
                continue
            entry['host'] = _host
            break
        elapsed = time.time() - start
        entry['elapsed_s'] = round(elapsed, 2)

        if r is None:
            entry['error'] = ('timeout' if _tried and all('timeout' in t for t in _tried)
                              else f'all hosts failed: {_tried}')
            _audit_log(entry)
            return None

        result = json.loads(r.stdout)

        if _use_chat:
            _msg = ((result.get('choices') or [{}])[0].get('message') or {})
            _usage = result.get('usage') or {}
            # gemma-4 输出走 deepseek reasoning 格式: 正文常在 reasoning_content
            _txt = (_msg.get('content') or '').strip()
            if not _txt:
                import re as _re2
                _rc = (_msg.get('reasoning_content') or '').strip()
                _m = _re2.findall(r'Action\s*[:：]\s*([^\n]+)', _rc)
                if _m:
                    _txt = _m[-1]
                else:
                    _best, _bi = _rc[-40:], -1
                    for _a in (actions or []):
                        _i = _rc.rfind(_a)
                        if _i > _bi:
                            _best, _bi = _a, _i
                    _txt = _best
            result = {'content': _txt,
                      'timings': {'prompt_n': _usage.get('prompt_tokens'),
                                  'predicted_n': _usage.get('completion_tokens')}}

        # token 计量 (2026-09-27): llama.cpp timings → prompt_n/predicted_n
        _tim = result.get('timings') if isinstance(result, dict) else None
        if isinstance(_tim, dict):
            if _tim.get('prompt_n') is not None:
                entry['prompt_tokens'] = _tim['prompt_n']
            if _tim.get('predicted_n') is not None:
                entry['response_tokens'] = _tim['predicted_n']

        if 'content' not in result:
            entry['error'] = f'no content in response: {r.stdout[:300]}'
            _audit_log(entry)
            return None

        raw_text = result['content'].strip()
        entry['raw_response'] = raw_text[:200]

        # 解析: 从 LLM 输出中提取动作名
        # LLM 可能会输出完整句子, 需要切词匹配
        if not actions:
            # 无动作列表: 返回原始文本, 由调用方做二次匹配
            # 取第一个看起来像动作的词
            import re as _re
            words = raw_text.strip().split()
            act = words[0].strip('"\'`.,!?:;()[] ') if words else ''
            if not act or len(act) < 2:
                entry['error'] = f'no usable action in: {raw_text[:80]}'
                _audit_log(entry)
                return None
            suggestion = {
                'act': act,
                'confidence': 0.5,
                'reasoning': raw_text[:200],
            }
            entry['suggestion'] = suggestion
            _audit_log(entry)
            return suggestion
        
        # 有动作列表: 逐词匹配 (大小写不敏感)
        words = raw_text.strip().split()
        matched_act = None
        for w in words:
            w_clean = w.strip('"\'`.,!?:;()[] ')
            if not w_clean:
                continue
            if w_clean in actions:
                matched_act = w_clean
                break
            for a in actions:
                if w_clean.lower() == a.lower():
                    matched_act = a
                    break
                if w_clean.lower() in a.lower() or a.lower() in w_clean.lower():
                    matched_act = a
                    break
            if matched_act:
                break
        
        # fallback: 子串匹配 — 在全文搜索动作名
        if not matched_act:
            for a in actions:
                if a in raw_text:
                    matched_act = a
                    break
        
        # F1 accept 契约 (2026-10-22): 候选必须严格 ∈ actions.
        # 已删旧版"取第一个看起来像动作的词"fallback (越界候选缺口 — 会把
        # 不在 actions 内的词当候选, 违反 vt ∈ A). 无匹配 ⇒ 拒收 None.
        if not matched_act:
            entry['out_of_vocab'] = raw_text[:100]
            entry['error'] = f'no matching action in {actions}'
            _audit_log(entry)
            return None
        act = matched_act

        # 置信度: 简单映射 — 用 token 数/n_predict 做粗略估计
        n_tokens = result.get('tokens_evaluated', 0) or 0
        confidence = 1.0 - min(1.0, max(0.0, n_tokens / 64.0))

        suggestion = {
            'act': act,
            'confidence': round(confidence, 3),
            'reasoning': raw_text[:200],
        }
        # F3 候选准入: 经确定性内核准入 (accept + confidence + 来源绑定)
        admitted = admit(suggestion, actions)
        entry['suggestion'] = admitted
        if admitted is None:
            entry['error'] = f'candidate rejected by accept contract: {act}'
            _audit_log(entry)
            return None
        _audit_log(entry)
        return admitted

    except subprocess.TimeoutExpired:
        entry['error'] = 'timeout'
        _audit_log(entry)
        return None
    except json.JSONDecodeError as e:
        entry['error'] = f'json parse: {e}'
        _audit_log(entry)
        return None
    except Exception as e:
        entry['error'] = f'unexpected: {e}'
        entry['traceback'] = traceback.format_exc()
        _audit_log(entry)
        return None


# ── self-test ─────────────────────────────────────────────
def _self_test():
    """健康检查 + 一次简单提示测试"""
    health = _health()
    if not health['ok']:
        return {'ok': False,
                'detail': f'llama.cpp unavailable: {health.get("error")}'}

    # 测试: 3 选 1
    r = suggest('box', 'open', current='closed',
                world_name='test_world',
                actions=['push', 'pull', 'lift'])
    if r and r.get('act') in ('push', 'pull', 'lift'):
        return {'ok': True,
                'detail': f'llm arm ready, suggestion: {r}'}
    return {'ok': False,
            'detail': f'test failed, result={r}'}


if __name__ == '__main__':
    import sys

    if '--health' in sys.argv:
        print(json.dumps(_health(), ensure_ascii=False))
        sys.exit(0)

    if '--test' in sys.argv:
        result = _self_test()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result['ok'] else 1)

    # 手动: python core/llm_arm.py <obj> <goal> [current] [world] [action1 action2 ...]
    if len(sys.argv) >= 3:
        r = suggest(
            obj=sys.argv[1],
            goal=sys.argv[2],
            current=sys.argv[3] if len(sys.argv) > 3 else None,
            world_name=sys.argv[4] if len(sys.argv) > 4 else '',
            actions=sys.argv[5:] if len(sys.argv) > 5 else None,
        )
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("Usage:")
        print("  python core/llm_arm.py --health          # 检查 llama.cpp 服务")
        print("  python core/llm_arm.py --test            # 全自测")
        print("  python core/llm_arm.py <obj> <goal> [current] [world] [action ...]")
        print("Env:")
        print("  LLM_ARM=1        启用 (默认关)")
        print("  LLM_ARM_HOST     默认 http://localhost:8082")
        print("  LLM_ARM_TIMEOUT  请求超时秒数 (默认 15)")
        print("  LLM_ARM_AUDIT_DIR  审计日志目录")