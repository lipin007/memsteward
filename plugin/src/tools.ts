// tools.ts — 治理工具四件（manifest contracts.tools 已声明，名称与注册严格一致）
//   governance_preflight  门禁：教训断言开机闸（pvs.gate boot）
//   governance_ledger     教训台账查询（13 条六字段）
//   governance_deposit    决策入账（提议带理由、决议带因果；入账即硬落盘）
//   governance_recall     签名门控召回（替代翻文件捞针）
import { Type } from "typebox";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core";
import { bridgeCallAsync, type BridgeConfig } from "./bridge.js";

export function registerGovernanceTools(
  api: OpenClawPluginApi,
  cfg: BridgeConfig,
): void {
  api.registerTool({
    name: "governance_preflight",
    description:
      "运行治理门禁（pvs.gate 开机闸）：13 条教训断言 + 记忆切片 + 真相摘要 + 依赖链巡检（deps_targets.json 存在时逐条真跑，死链入账）。开工前或用户要门禁读数时调用。",
    parameters: Type.Object({}),
    outputSchema: Type.Object(
      {
        ok: Type.Boolean(),
        n_fail: Type.Number(),
        n_decl: Type.Number(),
        rendered: Type.String(),
      },
      { additionalProperties: true },
    ),
    async execute(_id, _params) {
      const r = await bridgeCallAsync(cfg, "preflight");
      return {
        content: [{ type: "text", text: String(r.rendered ?? JSON.stringify(r)) }],
        details: r,
      };
    },
  });

  api.registerTool({
    name: "governance_ledger",
    description:
      "查询工程教训台账（pvs.gate）：不带 id 列出全部；带 id 取单条六字段（症状/根因/断言/教训/适用面/验证）。",
    parameters: Type.Object({ id: Type.Optional(Type.String()) }),
    outputSchema: Type.Object({}, { additionalProperties: true }),
    async execute(_id, params) {
      const args: string[] = params?.id ? ["--id", String(params.id)] : [];
      const r = await bridgeCallAsync(cfg, "ledger", args);
      return {
        content: [{ type: "text", text: JSON.stringify(r, null, 1) }],
        details: r,
      };
    },
  });

  api.registerTool({
    name: "governance_deposit",
    description:
      "决策入账（记忆生死层）：提议带理由、决议带因果入账，入账即原子落盘（进程死记忆不死）。只记拍板与已验证结论，不记过程流水。",
    parameters: Type.Object({
      obj: Type.String({ description: "对象/主题" }),
      act: Type.String({ description: "动作/决议" }),
      actual: Type.Optional(Type.String({ description: "实际结果/证据" })),
      cur: Type.Optional(Type.String({ description: "当前状态/口径" })),
    }),
    outputSchema: Type.Object({}, { additionalProperties: true }),
    async execute(_id, params) {
      const args = [
        "--obj", String(params.obj),
        "--act", String(params.act),
        "--actual", String(params.actual ?? ""),
        "--cur", String(params.cur ?? ""),
      ];
      const r = await bridgeCallAsync(cfg, "deposit", args);
      return {
        content: [{ type: "text", text: `已入账: ${r?.entry?.id ?? "?"}` }],
        details: r,
      };
    },
  });

  api.registerTool({
    name: "governance_recall",
    description:
      "签名门控召回：max(Jaccard, 查询覆盖率) ≥0.3 才出账，中文支持 bigram 部分匹配，被召回即保活。找「上次为什么这么定」用它，别翻文件。",
    parameters: Type.Object({
      signature: Type.String({ description: "查询签名（空格分隔的词）" }),
      k: Type.Optional(Type.Number({ description: "返回上限，默认 8" })),
    }),
    outputSchema: Type.Object({}, { additionalProperties: true }),
    async execute(_id, params) {
      const args = ["--signature", String(params.signature)];
      if (params.k) args.push("--k", String(Math.floor(Number(params.k))));
      const r = await bridgeCallAsync(cfg, "recall", args);
      return {
        content: [{ type: "text", text: JSON.stringify(r, null, 1) }],
        details: r,
      };
    },
  });
}
