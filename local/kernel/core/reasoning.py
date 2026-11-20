
"""因果检验真函数: granger_test + dmit_test (纯 numpy, 单一真源)

黄金骨架 (2026-08-14): 从原 reasoning.py 抄活不抄死 — 只保留
内核消费的真函数 (concept_principle DMIT 因果精化依赖), 向量侧死代码
(GrowthAlgorithm/CausalReasoner/torch) 一律不带。
"""
import numpy as np
from typing import Dict, List, Optional, Tuple


def granger_test(x_series, y_series, lag: int = 1) -> dict:
    """Granger 因果检验纯函数 (单一真源)

    2026-08-09 抽取: CausalReasoner.granger_causality 与
    ConceptSpace.learn_causal 共用此数学 (概念级/神经元级同一检验)。

    原理:
    - 模型1: 只用 Y 的历史预测 Y
    - 模型2: 用 Y 的历史 + X 的历史预测 Y
    - 如果模型2更好, 则 X Granger-causes Y

    Returns:
        {
            'f_stat_xy': float,  # X→Y F 统计量 (>3.84 则 p<0.05)
            'f_stat_yx': float,  # Y→X F 统计量
            'is_causal_xy': bool,
            'is_causal_yx': bool,
            'direction': str,  # 'X→Y' or 'Y→X' or '双向' or 'none'
            'is_causal': bool,  # direction != 'none'
        }
    """
    x = np.asarray(x_series, dtype=float)
    y = np.asarray(y_series, dtype=float)
    if len(x) < lag + 10 or len(y) < lag + 10:
        return {'f_stat_xy': 0.0, 'f_stat_yx': 0.0,
                'is_causal_xy': False, 'is_causal_yx': False,
                'direction': 'none', 'is_causal': False}
    # 构建滞后矩阵
    n = len(y) - lag
    Y = y[lag:]  # 目标 (shape: n)
    # 模型1: 只用 Y 的历史
    Y_lag = np.column_stack([y[lag - 1 - i:len(y) - 1 - i] for i in range(lag)])
    Y_lag_with_intercept = np.column_stack([np.ones(n), Y_lag])
    try:
        beta1 = np.linalg.lstsq(Y_lag_with_intercept, Y, rcond=None)[0]
        pred1 = Y_lag_with_intercept @ beta1
        rss1 = np.sum((Y - pred1) ** 2)
    except Exception:
        return {'f_stat_xy': 0.0, 'f_stat_yx': 0.0,
                'is_causal_xy': False, 'is_causal_yx': False,
                'direction': 'none', 'is_causal': False}
    # 模型2: 用 Y 的历史 + X 的历史
    X_lag = np.column_stack([x[lag - 1 - i:len(x) - 1 - i] for i in range(lag)])
    XY_lag = np.column_stack([np.ones(n), Y_lag, X_lag])
    try:
        beta2 = np.linalg.lstsq(XY_lag, Y, rcond=None)[0]
        pred2 = XY_lag @ beta2
        rss2 = np.sum((Y - pred2) ** 2)
    except Exception:
        return {'f_stat_xy': 0.0, 'f_stat_yx': 0.0,
                'is_causal_xy': False, 'is_causal_yx': False,
                'direction': 'none', 'is_causal': False}
    k1 = lag
    k2 = 2 * lag
    if rss2 == 0 or n - k2 <= 0:
        return {'f_stat_xy': 0.0, 'f_stat_yx': 0.0,
                'is_causal_xy': False, 'is_causal_yx': False,
                'direction': 'none', 'is_causal': False}
    f_stat = ((rss1 - rss2) / (k2 - k1)) / (rss2 / (n - k2))
    is_causal_xy = f_stat > 3.84
    # 检验反方向: Y→X
    X_target = x[lag:]
    X_lag2 = np.column_stack([x[lag - 1 - i:len(x) - 1 - i] for i in range(lag)])
    Y_lag2 = np.column_stack([y[lag - 1 - i:len(y) - 1 - i] for i in range(lag)])
    X_lag2_with_intercept = np.column_stack([np.ones(n), X_lag2])
    try:
        beta3 = np.linalg.lstsq(X_lag2_with_intercept, X_target, rcond=None)[0]
        pred3 = X_lag2_with_intercept @ beta3
        rss3 = np.sum((X_target - pred3) ** 2)
    except Exception:
        is_causal_yx = False
        f_stat_yx = 0.0
    else:
        XY_lag2 = np.column_stack([np.ones(n), X_lag2, Y_lag2])
        try:
            beta4 = np.linalg.lstsq(XY_lag2, X_target, rcond=None)[0]
            pred4 = XY_lag2 @ beta4
            rss4 = np.sum((X_target - pred4) ** 2)
            f_stat_yx = (((rss3 - rss4) / lag) / (rss4 / (n - 2 * lag))
                         if rss4 > 0 and n - 2 * lag > 0 else 0.0)
            is_causal_yx = f_stat_yx > 3.84
        except Exception:
            is_causal_yx = False
            f_stat_yx = 0.0
    if is_causal_xy and not is_causal_yx:
        direction = 'X→Y'
    elif is_causal_yx and not is_causal_xy:
        direction = 'Y→X'
    elif is_causal_xy and is_causal_yx:
        direction = '双向'
    else:
        direction = 'none'
    return {
        'f_stat_xy': float(f_stat),
        'f_stat_yx': float(f_stat_yx),
        'is_causal_xy': bool(is_causal_xy),
        'is_causal_yx': bool(is_causal_yx),
        'direction': direction,
        'is_causal': direction != 'none',
    }

def dmit_test(x_series, y_series, k: int = 1, bins: int = 4,
              min_score: float = 0.05) -> dict:
    """DMIT 延迟互信息方向性检验纯函数 (单一真源)

    2026-08-09 R2 新增: 证明流涌现实验发现 granger f 值对稀疏序列
    数值爆炸 (10^28 完美拟合伪相关), 换计数频率的互信息方向性判据。
    CausalReasoner / ConceptSpace 共用此数学 (单一真源)。

    原理: 若 X→Y, 则 X 的过去携带 Y 未来的信息:
        I(X_t; Y_{t+k}) > I(Y_t; X_{t+k})  (k>=1)
    对稀疏序列稳健 (离散化计数, 无回归拟合, 不会数值爆炸)。

    Args:
        x_series: 源序列
        y_series: 目标序列
        k: 延迟步数 (1 = 下一步)
        bins: 离散化分箱数 (默认 4)
        min_score: 方向性判定阈值 (默认 0.05)

    Returns:
        {
            'score': float,   # I(X→Y) - I(Y→X), >0 → X→Y
            'i_xy': float,    # I(X_t; Y_{t+k})
            'i_yx': float,    # I(Y_t; X_{t+k})
            'direction': str, # 'X→Y' or 'Y→X' or 'none'
            'is_causal': bool,
        }
    """
    x = np.asarray(x_series, dtype=float)
    y = np.asarray(y_series, dtype=float)
    n = len(x)
    if n <= k + 2 or len(y) != n:
        return {'score': 0.0, 'i_xy': 0.0, 'i_yx': 0.0,
                'direction': 'none', 'is_causal': False}

    def _mi(a, b):
        """离散化互信息 (计数频率, 稳健不爆炸)

        2026-08-18 万级批次改造: numpy 直方图向量化替代 Python
        双层 dict 循环 — 数学逐位一致 (2000 试随机对照 max_diff
        ~1e-16, 300 试 dmit_test 整体一致), 吞吐 ~5-10x。
        联合计数矩阵 + 边缘计数, 只累加非零联合格点。"""
        if a.min() == a.max() or b.min() == b.max():
            return 0.0
        ab = np.digitize(a, np.linspace(a.min(), a.max() + 1e-9, bins + 1)) - 1
        bb = np.digitize(b, np.linspace(b.min(), b.max() + 1e-9, bins + 1)) - 1
        m = len(a)
        H, _, _ = np.histogram2d(ab, bb, bins=bins,
                                 range=[[0, bins], [0, bins]])
        p_xy = H / m
        p_x = H.sum(axis=1) / m
        p_y = H.sum(axis=0) / m
        mask = p_xy > 0
        with np.errstate(divide='ignore', invalid='ignore'):
            log_term = np.log2(p_xy / (p_x[:, None] * p_y[None, :]) + 1e-12)
        return float(np.sum(p_xy[mask] * log_term[mask]))

    i_xy = _mi(x[:n - k], y[k:])   # X 过去 → Y 未来
    i_yx = _mi(y[:n - k], x[k:])   # Y 过去 → X 未来
    score = i_xy - i_yx
    if score > min_score:
        direction = 'X→Y'
    elif score < -min_score:
        direction = 'Y→X'
    else:
        direction = 'none'
    return {
        'score': float(score),
        'i_xy': float(i_xy),
        'i_yx': float(i_yx),
        'direction': direction,
        'is_causal': direction != 'none',
    }
