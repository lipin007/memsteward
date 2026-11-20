// index.ts — 通用治理中间件 OpenClaw 插件入口（骨架 v0.1）
// 三面注册：context-engine（三层记忆）＋ memory（账本摘要）＋ tools（治理四件）。
// 单源原则：业务逻辑全在 Python（LandingStore/pvs.gate/accept_contract），TS 只做调用面。
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core";
import { registerGovernanceTools } from "./src/tools.js";
import { registerGovernanceContextEngine } from "./src/context-engine.js";
import { registerGovernanceMemory } from "./src/memory-capability.js";
import { registerToolfaceHook } from "./src/toolface_hook.js";
import type { BridgeConfig } from "./src/bridge.js";

export default definePluginEntry({
  id: "memgate",
  name: "MemGate",
  description:
    "Three-layer memory (hot/warm/cold) + governance gate tools, bridged to the Python single-source.",
  register(api: OpenClawPluginApi) {
    // 插件配置面（sdk-setup.md: 配置经 api.pluginConfig 下发；形状对齐 manifest configSchema）
    const cfg = ((api as any).pluginConfig ?? {}) as BridgeConfig;
    registerGovernanceTools(api, cfg);
    registerGovernanceContextEngine(api, cfg);
    registerGovernanceMemory(api, cfg);
    registerToolfaceHook(api, cfg); // P4 动态工具面（gate.toolfaceHook 开关，默认关）
  },
});
