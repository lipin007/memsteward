// context-engine.ts — 三层记忆上下文引擎（热/温/冷）＋事前约束（治理纪律面）
//   热层 = 近窗消息（assemble 保留尾部 hotWindowMessages 条）
//   温层 = 签名召回的决策账本（LandingStore recall → systemPromptAddition）
//   冷层 = 全量转录审计（ingest 逐条入账，进程死记忆不死）
//   治理纪律面 = 教训断言常驻注入（事前约束：违规从"被拦"变"不被生成"；读失败 fail-soft）
// 压缩 = 委托模式（ownsCompaction:false + delegateCompactionToRuntime）：
//   官方内置压缩兜底——即使本引擎有 bug，上下文压缩由官方引擎托底（不会搞坏 OpenClaw）。
// 契约：transcriptSemantics 两声明 + commitTurn 原子幂等（advancementKey 判重）。
// 失败语义：写路径（ingest/commitTurn）抛错交给宿主失败隔离（自动降级 legacy，不吞错）；
//          读路径（assemble 召回/治理纪律面）fail-soft 零注入（记忆缺失不得阻断回复）。
import { delegateCompactionToRuntime } from "openclaw/plugin-sdk/core";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core";
import { readFileSync, statSync } from "node:fs";
import { bridgeCallAsync, type BridgeConfig } from "./bridge.js";
import { stubGate, scanMessages, applyStub, shadowLog } from "./thinking_stub.js"; // 包1（2026-11-15）

// ── P2 转接层灰度门（插件渐退：会话装配回调→本地桥到记忆体 daemon）──────────
// gate 文件 config/daemon_forward.json（每调用 stat，mtime/size 变即重读 ⇒ 开关即时，
// 回退＝enabled:false，无需重载）。三态语义：
//   关/名单外 ⇒ 原路径逐字节不变；名单内 ⇒ POST /decision 取决策（hits 同形状，
//   格式化仍走本文件原代码）；daemon 不可达/异常 ⇒ fail-soft 回退原路径（记忆缺失
//   不阻断回复）。gate 缺失/坏文件 = 门关。
interface DaemonForwardGate {
  enabled: boolean;
  endpoint?: string;
  sessions?: string[];
  timeoutMs?: number;
}

const __gateCache = new Map<string, { mtimeMs: number; size: number; gate: DaemonForwardGate | null }>();

function __gateFileFor(cfg: any): string {
  if (cfg && typeof cfg.daemonForwardFile === "string" && cfg.daemonForwardFile) {
    return cfg.daemonForwardFile;   // 测试/自定义注入点
  }
  return fileURLToPath(new URL("../config/daemon_forward.json", import.meta.url));
}

import { fileURLToPath } from "node:url";  // 顶层导入（提升）：修 .pathname 百分号编码陷阱（中文路径 %E5%95%86... 不能 statSync）

function __loadGate(cfg: any): DaemonForwardGate | null {
  const path = __gateFileFor(cfg);
  try {
    const st = statSync(path);
    const hit = __gateCache.get(path);
    if (hit && hit.mtimeMs === st.mtimeMs && hit.size === st.size) return hit.gate;
    const gate = JSON.parse(readFileSync(path, "utf8")) as DaemonForwardGate;
    __gateCache.set(path, { mtimeMs: st.mtimeMs, size: st.size, gate });
    return gate;
  } catch {
    return null;   // 缺失/坏文件 = 门关 = 原路径（零变化）
  }
}

function __forwardEndpoint(gate: DaemonForwardGate | null, sessionKey: string): string | null {
  if (!gate || !gate.enabled) return null;
  for (const p of gate.sessions ?? []) {
    if (p === "*" || (p && sessionKey.startsWith(p))) {
      return (gate.endpoint ?? "http://127.0.0.1:8877").replace(/\/$/, "");
    }
  }
  return null;
}

// SDK 形状（钉自 dist/*.d.ts；完整类型导入留待装机编译）
interface AssembleResult {
  messages: unknown[];
  estimatedTokens: number;
  systemPromptAddition?: string;
}
interface CompactResult {
  ok: boolean;
  compacted: boolean;
  reason?: string;
}

/** CJK-aware token estimator
 *
 * 系数经真 tokenizer 标定（llama-server /tokenize · North-Mini-Code-1.0-UD-Q4_K_M · 2026-11-08）：
 * CJK ≈0.8 token/字（17字13tok≈0.76）、非 CJK ≈0.18 token/字（56字10tok≈0.18/char）；
 * 四样本误差 ≤±14%。仅影响压缩阈值，接口保持兼容。
 * 勿改系数不改标定——改前先 /tokenize 重标（数字可指回）。
 */
export function estimateTokensForContent(content: unknown): number {
  if (content == null) return 0;
  
  const str = typeof content === "string" ? content : JSON.stringify(content);
  let tokens = 0;
  
  for (let i = 0; i < str.length; i++) {
    const ch = str[i];
    // CJK 字符范围：
    // - 中文：\u4e00-\u9fff
    // - 日文：\u3040-\u309f (平假名), \u30a0-\u30ff (片假名), \u3000-\u303f (标点)
    // - 韩文：\uac00-\ud7af (Hangul syllables)
    // - 其他：\u3400-\u4dbf (扩展A), \u20000-\u2a6df (扩展B), \u30000-\u3134f (扩展C)
    // 简单启发式：如果在基本 CJK 范围内，计为一个 token
    if ((ch >= "\u4e00" && ch <= "\u9fff") ||  // 中文
        (ch >= "\u3040" && ch <= "\u309f") ||  // 日文平假名
        (ch >= "\u30a0" && ch <= "\u30ff") ||  // 日文片假名
        (ch >= "\uac00" && ch <= "\ud7af") ||  // 韩文
        (ch >= "\u3400" && ch <= "\u4dbf") ||  // 中文扩展A
        (ch >= "\u20000" && ch <= "\u2a6df")) { // 中文扩展B
      tokens += 0.8;   // CJK ≈0.8 token/字（标定 0.76，略高取整）
    } else {
      tokens += 0.18;  // 非 CJK ≈5.6 字符/token（标定 0.18/char）
    }
  }
  
  return Math.ceil(tokens);
}

/** 从近期消息提炼召回签名（骨架口径：末条用户文本前 300 字符；后续换分词签名）。 */
function sigOf(messages: unknown[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m: any = messages[i];
    if (m?.role === "user") {
      // 签名提取（2026-11-17）：content 数组提取实际文本，不用 JSON 壳
      let t: string;
      if (typeof m.content === "string") {
        t = m.content;
      } else if (Array.isArray(m.content)) {
        t = m.content
          .map((blk: any) => (typeof blk === "string" ? blk : (blk?.thinking ?? blk?.text ?? blk?.content ?? "")))
          .filter(Boolean)
          .join(" ");
      } else {
        t = JSON.stringify(m.content ?? "");
      }
      return t.slice(0, 300);
    }
  }
  return "";
}

// ── 事前约束（治理纪律面）：教训断言常驻注入，进程级缓存 ─────────────────────
let constraintsCache: string | null = null;

/** 取治理纪律面段落（进程级缓存；获取失败 fail-soft 返回 undefined，失败不缓存）。 */
export async function __constraintsFor(cfg: BridgeConfig): Promise<string | undefined> {
  if (constraintsCache !== null) return constraintsCache || undefined;
  try {
    const r: any = await bridgeCallAsync(cfg, "constraints");
    const lines: string[] = r?.lines ?? [];
    constraintsCache = lines.length
      ? "## 治理治理纪律面（事前约束·教训断言常驻）\n" + lines.map((l: string) => `- ${l}`).join("\n")
      : "";
    return constraintsCache || undefined;
  } catch (e) {
    console.error("[memgate] 治理纪律面获取失败（fail-soft 零注入）:", e);
    return undefined;
  }
}

/** 测试钩子：清治理纪律面缓存（生产不调用）。 */
export function __resetConstraintsForTest(): void {
  constraintsCache = null;
}

// ── 冷层自补投递（P0）─────────────────────────────────────────────────
// 病灶：宿主 deferredTurn 路径只调 assemble 不调 ingest ⇒ 冷层审计断供（2026-11-04 体检实锤）。
// 修法（引擎侧，独立于宿主）：assemble 时按内容哈希水位差量补投；与宿主 ingest() 共用水位表，
// 双投由 LandingStore 同构合并兜底（hits 语义，W4 回归）。水位只在实投后前进，突发限速余量下轮续投。
const __ingestedWm = new Map<string, Map<string, true>>(); // sessionId → (msgKey → true，插入序=淘汰序)

function __msgKeyOf(m: any): string {
  const role = String(m?.role ?? "?");
  const text = typeof m?.content === "string" ? m.content : JSON.stringify(m?.content ?? "");
  return role + "\u0000" + text;
}

function __wmFor(sessionId?: string): Map<string, true> {
  const key = String(sessionId ?? "_");
  let wm = __ingestedWm.get(key);
  if (!wm) {
    wm = new Map();
    __ingestedWm.set(key, wm);
    if (__ingestedWm.size > 200) {
      // 会话水位表限容：淘汰最老会话（其后重投由同构合并兜底，不腐账）
      const first = __ingestedWm.keys().next().value;
      if (first !== undefined) __ingestedWm.delete(first);
    }
  }
  return wm;
}

async function __ingestMessage(
  cfg: BridgeConfig,
  message: any,
  wm?: Map<string, true>,
): Promise<void> {
  const role = String(message?.role ?? "?");
  // 文本提取（2026-11-17）：content 是数组时提取实际文本字段（thinking/text/content），
  // 不存 JSON 壳——修复「教训埋在 JSON 里搜不到」的根本 bug。
  let text: string;
  if (typeof message?.content === "string") {
    text = message.content;
  } else if (Array.isArray(message?.content)) {
    text = message.content
      .map((blk: any) => {
        if (typeof blk === "string") return blk;
        return blk?.thinking ?? blk?.text ?? blk?.content ?? "";
      })
      .filter(Boolean)
      .join(" ");
  } else {
    text = JSON.stringify(message?.content ?? "");
  }
  await bridgeCallAsync(cfg, "ingest", ["--role", role, "--text", text.slice(0, 2000)]);
  if (wm) {
    wm.set(__msgKeyOf(message), true);
    while (wm.size > 6000) {
      const k = wm.keys().next().value;
      if (k === undefined) break;
      wm.delete(k);
    }
  }
}

const __SUPPLY_BURST = 200; // 每 assemble 至多补投条数（余量下轮续投）

async function __supplementIngest(
  cfg: BridgeConfig,
  sessionId: string | undefined,
  messages: unknown[],
): Promise<void> {
  const wm = __wmFor(sessionId);
  let n = 0;
  for (const m of messages) {
    if (n >= __SUPPLY_BURST) break;
    const k = __msgKeyOf(m);
    if (wm.has(k)) continue;
    await __ingestMessage(cfg, m, wm);
    n++;
  }
}

export function registerGovernanceContextEngine(
  api: OpenClawPluginApi,
  cfg: BridgeConfig,
): void {
  api.registerContextEngine("memgate", () => {
    const hotN = cfg.hotWindowMessages ?? 12;
    return {
      info: {
        id: "memgate",
        name: "Governance Middleware Context Engine",
        ownsCompaction: false, // 委托模式：压缩零丢失判据通过前不接管
        acceptedHostParams: ["sessionKey", "runtimeContext"],
        transcriptSemantics: {
          currentTurnFence: "before-current-turn-entry-v1",
          turnAdvancementIdempotency: "atomic-idempotent-v1",
        },
      },

      async ingest({ sessionId, message }: any): Promise<{ ingested: boolean }> {
        // 冷层：逐条入账（硬落盘）。写失败＝如实抛错，交宿主隔离（不静默吞）。
        await __ingestMessage(cfg, message, __wmFor(sessionId));
        return { ingested: true };
      },

      async assemble({ sessionId, sessionKey, messages, tokenBudget }: any): Promise<AssembleResult> {
        // 冷层自补投递（P0）：宿主 deferredTurn 不调 ingest ⇒ 这里按水位差量补投（去重）。
        await __supplementIngest(cfg, sessionId, messages ?? []);
        const hot: unknown[] = (messages ?? []).slice(-hotN);
        // 骨架 token 估算：使用 CJK 感知估算器
        const estimatedTokens = estimateTokensForContent(hot);
        const parts: string[] = [];
        const ban = await __constraintsFor(cfg);
        if (ban) parts.push(ban);
        // 精华教训主动注入（2026-11-17）：教训/铁律类高价值记忆自动带入上下文，
        // 不依赖 agent 主动查询——每次推理自动附带 top 教训提醒。
        try {
          const ess = await bridgeCallAsync(cfg, "recall", [
            "--signature", "教训|铁律|事故|根因|禁止|拍板", "--k", "8"]);
          const essHits = (ess as any)?.hits ?? [];
          if (essHits.length > 0) {
            parts.push(
              "## 历史教训提醒（教训优先·自动注入）\n" +
              essHits.map((h: any, i: number) =>
                `${i + 1}. ${h.entry?.signature ?? "?"}`).join("\n"));
          }
        } catch { /* fail-soft：教训注入失败不阻断 */ }

        // ── P2 转接层灰度门：名单内会话转发记忆体 daemon 取决策 ──────────
        const sk = String(sessionKey ?? sessionId ?? "");
        const fwd = __forwardEndpoint(__loadGate(cfg), sk);
        let decided = false;
        if (fwd) {
          try {
            const gate = __loadGate(cfg);
            const resp = await fetch(fwd + "/decision", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({
                session: sk, signature: sigOf(messages ?? []), k: 6,
                messages: (messages ?? []).slice(-200),
                total_messages: (messages ?? []).length,
              }),
              signal: AbortSignal.timeout(gate?.timeoutMs ?? 2500),
            });
            const rd: any = await resp.json();
            if (!rd?.ok || !Array.isArray(rd.hits)) {
              throw new Error(`daemon decision bad payload: ${resp.status}`);
            }
            const hits: any[] = rd.hits;
            if (hits.length) {
              parts.push(
                "## 决策记忆召回（温层·签名门控）\n" +
                  hits
                    .map((h: any) => `- ${h.entry?.signature ?? "?"}（相似度 ${h.score}）`)
                    .join("\n"),
              );
            }
            decided = true;   // 决策来自 daemon（0 命中也是决策，不回退原路径）
          } catch (e) {
            console.error("[memgate] 转接失败（fail-soft 回退原路径）:", e);
          }
        }
        if (!decided) {
          try {
            const r: any = await bridgeCallAsync(cfg, "recall", [
              "--signature", sigOf(messages ?? []), "--k", "6",
            ]);
            const hits: any[] = r?.hits ?? [];
            if (hits.length) {
              parts.push(
                "## 决策记忆召回（温层·签名门控）\n" +
                  hits
                    .map((h: any) => `- ${h.entry?.signature ?? "?"}（相似度 ${h.score}）`)
                    .join("\n"),
              );
            }
          } catch (e) {
            console.error("[memgate] 温层召回失败（fail-soft 零注入）:", e);
          }
        }
        void tokenBudget; // 骨架不预算裁剪；冷启动包预算留待 D 段实装
        // ── 包1 thinkingStub（2026-11-15）：历史 assistant 轮 thinking 短占位 ──
        // gate = config/thinking_stub.json 热读（缺省/坏文件 = off = 零行为变化）。
        // shadow = 零改写只落读数（命中轮数＋投影省额 → 记忆体/shadow/logs/）；
        // on = 替换非空短占位（❌空串/裸剥＝重建计费省 0，billing_anomaly §4 裁决）。
        // 存储面不动（ingest/commitTurn 原样），只动出站 messages[]；tool_call 不触碰。
        const stub = stubGate();
        let outMsgs = hot;
        if (stub.mode !== "off") {
          const scan = scanMessages(hot, stub.stubText);
          shadowLog(stub, String(sessionKey ?? sessionId ?? ""), scan);
          if (stub.mode === "on") outMsgs = applyStub(hot, stub.stubText);
        }
        return {
          messages: outMsgs,
          estimatedTokens: outMsgs === hot ? estimatedTokens : estimateTokensForContent(outMsgs),
          systemPromptAddition: parts.length ? parts.join("\n\n") : undefined,
        };
      },

      async compact(params: any): Promise<CompactResult> {
        // 委托模式：官方内置压缩兜底（文档标准形态，非偷懒——ownsCompaction:false 的契约路径）
        return (await delegateCompactionToRuntime(params)) as CompactResult;
      },

      async commitTurn({ advancementKey, messages }: any): Promise<{ status: string }> {
        // 原子幂等落盘：同 key 判 duplicate。写失败抛错 → 宿主失败隔离（不假报 committed）。
        const payload = JSON.stringify(messages ?? []).slice(0, 200);
        const r: any = await bridgeCallAsync(cfg, "commit", [
          "--key", String(advancementKey), "--payload", payload,
        ]);
        return { status: r.status === "duplicate" ? "duplicate" : "committed" };
      },
    };
  });
}
