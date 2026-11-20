#!/usr/bin/env python3
"""MemSteward × LangChain 集成示例"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared', 'llm'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'C-本地版', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'MemGate', 'src'))

from langchain_adapter import MemStewardMemory, check_langchain_compat

print("🔗 MemSteward × LangChain 集成")
print("=" * 50)

compat = check_langchain_compat()
print(f"LangChain: {compat['langchain']}")
print(f"MemSteward: {compat['memsteward']}")

# LangChain 标准接口
memory = MemStewardMemory(persist_path='/tmp/langchain_demo.json')

# save_context (LangChain 标准)
memory.save_context({'input': '我在挖矿'}, {'output': '小心岩浆!'})
memory.save_context({'input': '找到钻石了'}, {'output': '太棒了!'})
memory.save_context({'input': '被苦力怕炸了'}, {'output': '下次放个盾牌'})

# load_memory_variables (LangChain 标准)
result = memory.load_memory_variables({'input': '挖矿'})
print(f"\n检索结果:\n{result['history']}")

# MemSteward 独有能力
print(f"\n统计: {memory.stats()}")
print("\n✅ LangChain 集成工作正常")
