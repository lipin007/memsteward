# MANIFEST — A-插件版 物料清单（2026-11-19 组合审查修正: 依实 import 面改写）

> 版本: v2026.11.19（CalVer）

## 组合清单（实 import 证据: bridge_cli/admission/m3 件）

| # | 件 | 用途 |
|---|---|---|
| 1 | tokenizer | 中英分词 |
| 2 | quality_gate | 质量门 |
| 3 | knowledge_distiller | 蒸馏 |
| 4 | hebbian_link | 共现/查询扩展 |
| 5 | tiered_decay | compact 衰减 |
| 7/8 | landing_store/summarizer | 落盘/摘要（calldecacy 包内） |
| 9 | memgate | 打包链（pack.sh/plugin.json） |
| 10 | mechanism_learn | 机制学习（m3 链消费） |
| 12 | m3 | 采集器+判读（A 树平铺影子） |
| 20 | calldecacy-sdk | 记忆引擎整包 |
| 21 | admission | 写入准入 |
| 22 | semantic_recall | 语义臂 hybrid_recall |

> 组合审查修正：移除 #6 memory_core（A 实不 import，原报虚）；补 #2/#10/#21/#22（原漏报）。

## 产品本体

bridge_cli.py（与 B 同文）/ MemGate 测试床（test/ 83 判据）

## 安装形态

npm/tgz 插件；`_bootstrap` 随包 vendor 优先；家 `MEMSTEWARD_HOME`

## 变更流

改组件→正源→sync_kernel→八门→本件→COMPONENTS.md 记一行
