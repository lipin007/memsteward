// memory-capability.ts — 记忆槽注册（plugins.slots.memory 候选）
// 形状钉自 2026.9.4 dist/*.d.ts：
//   MemoryPluginCapability = { promptBuilder?: (params) => string[]; deterministicRecallToolName?; ... }
//   MemoryPromptSectionParams = { availableTools: Set<string>; citationsMode?; agentId?; agentSessionKey?; sandboxed? }
// promptBuilder 是同步签名 → 走 bridgeCall 同步桥；失败 fail-soft 零注入（记忆缺失不阻断回复）。
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core";
import { bridgeCall, type BridgeConfig } from "./bridge.js";

interface MemoryPromptSectionParams {
  availableTools: Set<string>;
  citationsMode?: string;
  agentId?: string;
  agentSessionKey?: string;
  sandboxed?: boolean;
}

export function registerGovernanceMemory(
  api: OpenClawPluginApi,
  cfg: BridgeConfig,
): void {
  api.registerMemoryCapability({
    // 确定性召回工具由本插件的 governance_recall 提供（provider 直查的落点）
    deterministicRecallToolName: "governance_recall",
    promptBuilder: (params: MemoryPromptSectionParams): string[] => {
      void params; // 骨架摘要不区分会话；D 段按 agentSessionKey 定向
      try {
        const r: any = bridgeCall(cfg, "digest", ["--k", "8"]);
        const top: any[] = r?.top ?? [];
        if (!top.length) return [];
        const lines = top.map(
          (e: any) => `- ${e.signature ?? "?"}（hits=${e.hits}，${e.ts ?? "?"}）`,
        );
        return [
          "## 决策记忆（温层·账本摘要）\n" +
            lines.join("\n") +
            "\n（检索：governance_recall 工具；入账：governance_deposit）",
        ];
      } catch (e) {
        console.error("[memgate] 记忆摘要失败（fail-soft 零注入）:", e);
        return [];
      }
    },
  });
}
