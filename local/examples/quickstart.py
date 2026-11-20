#!/usr/bin/env python3
"""MemSteward 快速开始 — 5 分钟上手"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'C-本地版', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'MemGate', 'src'))

from memsteward_local import MemStewardLocal

print("🚀 MemSteward 快速开始")
print("=" * 50)

# 1. 初始化 (持久化到文件)
mem = MemStewardLocal(persist_path='/tmp/memsteward_demo.json')
print("✅ 初始化完成")

# 2. 写记忆 (自动过质量门)
print("\n📝 写入记忆...")
mem.deposit('玩家', '挖矿', '在洞穴深处找到钻石', kind='experience')
mem.deposit('玩家', '建造', '用木头建了小屋', kind='experience')
mem.deposit('玩家', '战斗', '被僵尸袭击但活下来', kind='experience')
mem.deposit('', '', '', kind='junk')  # 空内容会被质量门拦截
print(f"   写入 {mem.stats()['n_entries']} 条 (垃圾被拦)")

# 3. 语义检索
print("\n🔍 语义检索 '挖矿'...")
hits = mem.recall('挖矿', top_k=3)
for h in hits:
    print(f"   {h['obj']} {h['act']}: {h['actual']}")

# 4. 时间线
print("\n⏰ 时间线...")
recent = mem.recall_recent(hours=1)
for e in recent:
    ts = time.strftime('%H:%M:%S', time.localtime(e.get('timestamp', 0)))
    print(f"   [{ts}] {e['obj']} {e['act']}")

# 5. liveness 衰减
print("\n📉 liveness 衰减...")
mem.deposit('旧记忆', '很久以前', '发生的事', kind='experience')
for _ in range(30):
    mem.decay(0.95)
hits = mem.recall('旧记忆', top_k=1)
if hits:
    print(f"   30次衰减后 liveness: {hits[0].get('liveness', 1.0):.4f}")

# 6. 统计
print(f"\n📊 统计: {mem.stats()}")
print("\n✅ 完成! 这就是 MemSteward。")
