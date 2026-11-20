#!/usr/bin/env python3
"""
core/concept_space.py — 概念空间 (语义记忆, 本体) [S3 拆分后组装入口]

2026-08-11 S3 施工 (用户拍板 P2①): 单文件 3656 行 → 5 子模块 mixin:
  ontology (数据结构/激活/奖励/观察/感知命名, 954 行)
  phase    (相位场 + 三档新颖 + 内分泌, 479 行)
  principle(因果学习 + 原理引擎, 540 行)
  state    (状态链/过程推演/推断/规划/deduce, 902 行)
  space    (因果查询/记忆/问答/序列化, 689 行)

零机制变更: 方法体一字未改, 仅归位; `from core.concept_space import
ConceptSpace` 兼容不变 (102 处引用零改动)。
"""
from core.concept_ontology import ConceptSpaceOntologyMixin
from core.concept_phase import ConceptSpacePhaseMixin
from core.concept_principle import ConceptSpacePrincipleMixin
from core.concept_state import ConceptSpaceStateMixin
from core.concept_space_mixin import ConceptSpaceSpaceMixin
from core.concept_pyramid import ConceptPyramidMixin
from core.concept_opposition import ConceptSpaceOppositionMixin
# 常量重导出 (research_act_skills3 等实验脚本引用)
from core.concept_ontology import (
    PERSON, ACTION, OBJECT, EMOTION,
)


class ConceptSpace(ConceptSpaceOntologyMixin,
                   ConceptSpacePhaseMixin,
                   ConceptSpacePrincipleMixin,
                   ConceptSpaceStateMixin,
                   ConceptSpaceSpaceMixin,
                   ConceptPyramidMixin,
                   ConceptSpaceOppositionMixin):
    """概念空间 (语义记忆, 本体) — 7 子模块 mixin 组装

    方法按 C1 14 区块归位到 6 子模块 (见各模块文件头), 本类仅组装。
    保持 `from core.concept_space import ConceptSpace` 兼容。
    (2026-09-03: +ConceptPyramidMixin 多级概念金字塔; 自治域装配
    默认开 — run_lifeform 设 pyramid_enabled, 判断标准=是否让项目更好)
    (2026-09-04: +ConceptSpaceOppositionMixin 符号层对立结构 (B 路线
    落地, 默认关零破坏); 研究 → knowledge/opposition_selectivity_
    research_conclusion_20260904.md)
    """
    pass
