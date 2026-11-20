// thinking_stub.ts — 包1 历史轮 thinking 短占位替换（2026-11-15 实施卡·billing_anomaly §4/§5 放行）
// 形态锁死（跑前预注册）：
//   ✅ 仅非空短占位「（历史思考已省略）」（108 字符级）——§5.2 已证不触发服务端重建计费
//   ❌ 裸剥字段/空串 —— 已证被重建计费（prompt_tokens ≈ 全量 thinking，省 0），出局
//   ❌ 不动 tool_call ID（占位优先于重写）
//   只动历史 assistant 轮的 thinking 文本；user / toolResult / 新生成轮不动。
// 开关：config/thinking_stub.json（与 daemon_forward.json 同级，stat mtime/size 热读，即时生效）。
//   mode: "off"（缺省/坏文件=关=零行为变化）| "shadow"（只统计命中轮数＋投影省额，零改写）| "on"（替换）
// 影子读数：记忆体/shadow/logs/thinking_stub_shadow.jsonl（fail-soft：写失败不得阻断回复）。
// redacted_thinking 块不替换（signature 语义，见 impl_report 红牌记录）。
import { appendFileSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

export const STUB_TEXT = "（历史思考已省略）"; // 108 字符级短占位（probe_quality B_stub 同款，逐字节对齐）

export interface StubGate {
  mode: "off" | "shadow" | "on";
  stubText: string;
  logDir: string;
}

const GATE_FILE = fileURLToPath(new URL("../config/thinking_stub.json", import.meta.url));
const DEFAULT_LOG_DIR = fileURLToPath(new URL("../../记忆体/shadow/logs/", import.meta.url));
const __cache = new Map<string, { mtimeMs: number; size: number; gate: StubGate }>();

/** 热读开关（与 __loadGate 同机制：mtime/size 变即重读；缺失/坏文件 = off = 零行为变化）。 */
export function stubGate(): StubGate {
  try {
    const st = statSync(GATE_FILE);
    const hit = __cache.get(GATE_FILE);
    if (hit && hit.mtimeMs === st.mtimeMs && hit.size === st.size) return hit.gate;
    const g = JSON.parse(readFileSync(GATE_FILE, "utf8"));
    const mode = g?.mode === "shadow" || g?.mode === "on" ? g.mode : "off";
    const gate: StubGate = {
      mode,
      stubText: typeof g?.stubText === "string" && g.stubText ? g.stubText : STUB_TEXT,
      logDir: typeof g?.logDir === "string" && g.logDir ? g.logDir : DEFAULT_LOG_DIR,
    };
    __cache.set(GATE_FILE, { mtimeMs: st.mtimeMs, size: st.size, gate });
    return gate;
  } catch {
    return { mode: "off", stubText: STUB_TEXT, logDir: DEFAULT_LOG_DIR };
  }
}

export interface StubScan {
  hitTurns: number; // 含非空可替换 thinking 的历史 assistant 轮数
  thinkChars: number; // 可替换 thinking 字符数（替换后省掉的输入面）
  redactedSkipped: number; // redacted_thinking 块跳过数（不动，signature 语义）
}

/** 单条消息可替换 thinking 扫描（内部块形态优先；wire 形态 reasoning_content 兜底）。 */
function scanMessage(m: any, stubText: string): { chars: number; hit: number; redacted: number } {
  if (String(m?.role ?? "") !== "assistant") return { chars: 0, hit: 0, redacted: 0 };
  const content = m?.content;
  let chars = 0;
  let redacted = 0;
  let sawThinkingBlock = false;
  if (Array.isArray(content)) {
    for (const b of content) {
      if (!b || typeof b !== "object") continue;
      if (b.type === "thinking") {
        sawThinkingBlock = true;
        const t = String(b.thinking ?? "");
        if (t && t !== stubText) chars += t.length;
      } else if (b.type === "redacted_thinking") {
        sawThinkingBlock = true;
        redacted += 1; // 不可替换（加密 payload 在 signature），不计省额
      }
    }
  }
  if (!sawThinkingBlock) {
    const rc = m?.reasoning_content;
    if (typeof rc === "string" && rc && rc !== stubText) chars += rc.length;
  }
  return { chars, hit: chars > 0 ? 1 : 0, redacted };
}

/** 影子扫描：零改写，只出读数（命中轮数＋可替换 thinking 字符数）。 */
export function scanMessages(messages: unknown[], stubText: string): StubScan {
  let hitTurns = 0;
  let thinkChars = 0;
  let redactedSkipped = 0;
  for (const m of messages ?? []) {
    const s = scanMessage(m, stubText);
    hitTurns += s.hit;
    thinkChars += s.chars;
    redactedSkipped += s.redacted;
  }
  return { hitTurns, thinkChars, redactedSkipped };
}

/** on 档替换：历史 assistant 轮 thinking 文本 → 非空短占位（浅拷贝，不动原数组；tool_call 不触碰）。 */
export function applyStub(messages: unknown[], stubText: string): unknown[] {
  return (messages ?? []).map((m: any) => {
    if (String(m?.role ?? "") !== "assistant") return m;
    const content = m?.content;
    if (Array.isArray(content)) {
      let touched = false;
      const next = content.map((b: any) => {
        if (b && typeof b === "object" && b.type === "thinking") {
          const t = String(b.thinking ?? "");
          if (t && t !== stubText) {
            touched = true;
            return { ...b, thinking: stubText }; // 只换文本；signature/redacted 不触碰
          }
        }
        return b;
      });
      return touched ? { ...m, content: next } : m;
    }
    const rc = m?.reasoning_content;
    if (typeof rc === "string" && rc && rc !== stubText) {
      return { ...m, reasoning_content: stubText };
    }
    return m;
  });
}

/** 影子读数落盘（fail-soft；tok/¥ 投影用 levers 口径：CPT=3.0 chars/tok，in_miss ¥3/M，cache_hit ¥0.025/M）。 */
export function shadowLog(gate: StubGate, sessionKey: string, scan: StubScan): void {
  if (scan.hitTurns === 0 && scan.thinkChars === 0) return; // 零命中不落行（减噪音；总量由重放脚本统计）
  try {
    mkdirSync(gate.logDir, { recursive: true });
    const tok = scan.thinkChars / 3.0; // levers CPT=3.0
    const rec = {
      ts: new Date().toISOString(),
      session: String(sessionKey ?? ""),
      hit_turns: scan.hitTurns,
      think_chars: scan.thinkChars,
      redacted_skipped: scan.redactedSkipped,
      proj_tok: Math.round(tok),
      proj_yuan_miss: +(tok / 1e6 * 3.0).toFixed(4), // 未命中价口径（上界）
      proj_yuan_cache: +(tok / 1e6 * 0.025).toFixed(4), // 缓存命中价口径（下界）
    };
    appendFileSync(join(gate.logDir, "thinking_stub_shadow.jsonl"), JSON.stringify(rec) + "\n");
  } catch {
    /* fail-soft：读数写失败不得阻断回复 */
  }
}
