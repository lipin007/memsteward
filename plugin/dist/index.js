// index.ts
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

// src/tools.ts
import { Type } from "typebox";

// src/bridge.ts
import { execFileSync, spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
var DEFAULT_BRIDGE = fileURLToPath(new URL("./bridge_cli.py", import.meta.url));
function flagTail(cfg, args) {
  const tail = [];
  if (cfg.landingPath) tail.push("--landing", cfg.landingPath);
  if (cfg.workspaceRoot) tail.push("--ws", cfg.workspaceRoot);
  return tail.concat(args.map(String));
}
function bridgeCall(cfg, sub, args = []) {
  const bin = cfg.pythonBin ?? "python3";
  const bridge = cfg.bridgePath ?? DEFAULT_BRIDGE;
  const out = execFileSync(bin, [bridge, "--oneshot"], {
    input: JSON.stringify({ sub, args: flagTail(cfg, args) }),
    encoding: "utf-8",
    timeout: 5e3,
    // 同步面仅 promptBuilder（实测 warm 10–20ms ⇒ 250×余量）；python 挂死最坏卡事件循环 5s 而非 30s，保登录页可用
    maxBuffer: 8 * 1024 * 1024
  });
  return JSON.parse(out);
}
var BridgeWorker = class {
  constructor(cfg) {
    this.cfg = cfg;
  }
  cfg;
  proc = null;
  nextId = 1;
  pending = /* @__PURE__ */ new Map();
  buf = "";
  ensure() {
    if (this.proc && this.proc.exitCode === null) return this.proc;
    const bin = this.cfg.pythonBin ?? "python3";
    const bridge = this.cfg.bridgePath ?? DEFAULT_BRIDGE;
    const proc = spawn(bin, [bridge, "--serve"], { stdio: ["pipe", "pipe", "pipe"] });
    this.buf = "";
    proc.stdout.on("data", (d) => this.onData(d));
    proc.stderr.on("data", (d) => {
      const s = d.toString().trim();
      if (s) console.error("[memgate] worker stderr:", s.slice(0, 500));
    });
    proc.on("exit", () => this.onExit(proc));
    proc.on("error", (err) => this.onError(proc, err));
    this.proc = proc;
    return proc;
  }
  onData(d) {
    this.buf += d.toString("utf-8");
    let nl;
    while ((nl = this.buf.indexOf("\n")) >= 0) {
      const line = this.buf.slice(0, nl).trim();
      this.buf = this.buf.slice(nl + 1);
      if (!line) continue;
      let msg;
      try {
        msg = JSON.parse(line);
      } catch {
        continue;
      }
      const p = this.pending.get(msg.id);
      if (!p) continue;
      this.pending.delete(msg.id);
      clearTimeout(p.timer);
      if (msg.ok) p.resolve(msg.result);
      else p.reject(new Error(String(msg.error ?? "bridge worker error")));
    }
  }
  onExit(proc) {
    if (this.proc === proc) this.proc = null;
    for (const [, p] of this.pending) {
      clearTimeout(p.timer);
      p.reject(new Error("bridge worker exited"));
    }
    this.pending.clear();
  }
  onError(proc, err) {
    if (this.proc === proc) this.proc = null;
    for (const [, p] of this.pending) {
      clearTimeout(p.timer);
      p.reject(new Error(`bridge worker spawn: ${err.message}`));
    }
    this.pending.clear();
  }
  call(sub, tail) {
    return new Promise((resolve, reject) => {
      const proc = this.ensure();
      const id = this.nextId++;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        this.dispose();
        reject(new Error(`bridge worker timeout: ${sub}`));
      }, 3e4);
      this.pending.set(id, { resolve, reject, timer });
      proc.stdin.write(JSON.stringify({ id, sub, args: tail }) + "\n", (err) => {
        if (!err) return;
        const p = this.pending.get(id);
        if (p) {
          this.pending.delete(id);
          clearTimeout(p.timer);
          this.dispose();
          p.reject(new Error(`bridge worker write: ${err.message}`));
        }
      });
    });
  }
  dispose() {
    const proc = this.proc;
    this.proc = null;
    for (const [, p] of this.pending) {
      clearTimeout(p.timer);
      p.reject(new Error("bridge worker disposed"));
    }
    this.pending.clear();
    if (proc && proc.exitCode === null) proc.kill("SIGTERM");
  }
};
var GATE_CFG = fileURLToPath(new URL("../config/daemon_forward.json", import.meta.url));
function remoteFor(cfg) {
  if (cfg.remoteBridge === false) return null;
  if (cfg.remoteEndpoint) return cfg.remoteEndpoint;
  try {
    const g = JSON.parse(readFileSync(GATE_CFG, "utf-8"));
    if (g && g.bridgeRemote && typeof g.endpoint === "string") return g.endpoint;
  } catch {
  }
  return null;
}
async function remoteCall(endpoint, sub, tail) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 25e3);
  try {
    const res = await fetch(endpoint.replace(/\/$/, "") + "/bridge", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sub, args: tail }),
      signal: ac.signal
    });
    const body = await res.json();
    if (!res.ok || body && body.ok === false && body.error) {
      throw new Error(String(body?.error ?? `HTTP ${res.status}`));
    }
    return body && typeof body === "object" && body.ok === true && "result" in body ? body.result : body;
  } finally {
    clearTimeout(timer);
  }
}
var workers = /* @__PURE__ */ new Map();
function workerFor(cfg) {
  const key = `${cfg.pythonBin ?? "python3"}|${cfg.bridgePath ?? DEFAULT_BRIDGE}`;
  let w = workers.get(key);
  if (!w) {
    w = new BridgeWorker(cfg);
    workers.set(key, w);
  }
  return w;
}
function bridgeCallAsync(cfg, sub, args = []) {
  const tail = flagTail(cfg, args);
  const ep = remoteFor(cfg);
  if (ep) return remoteCall(ep, sub, tail).catch(() => workerFor(cfg).call(sub, tail));
  return workerFor(cfg).call(sub, tail);
}

// src/tools.ts
function registerGovernanceTools(api, cfg) {
  api.registerTool({
    name: "governance_preflight",
    description: "\u8FD0\u884C\u6CBB\u7406\u95E8\u7981\uFF08pvs.gate \u5F00\u673A\u95F8\uFF09\uFF1A13 \u6761\u6559\u8BAD\u65AD\u8A00 + \u8BB0\u5FC6\u5207\u7247 + \u771F\u76F8\u6458\u8981 + \u4F9D\u8D56\u94FE\u5DE1\u68C0\uFF08deps_targets.json \u5B58\u5728\u65F6\u9010\u6761\u771F\u8DD1\uFF0C\u6B7B\u94FE\u5165\u8D26\uFF09\u3002\u5F00\u5DE5\u524D\u6216\u7528\u6237\u8981\u95E8\u7981\u8BFB\u6570\u65F6\u8C03\u7528\u3002",
    parameters: Type.Object({}),
    outputSchema: Type.Object(
      {
        ok: Type.Boolean(),
        n_fail: Type.Number(),
        n_decl: Type.Number(),
        rendered: Type.String()
      },
      { additionalProperties: true }
    ),
    async execute(_id, _params) {
      const r = await bridgeCallAsync(cfg, "preflight");
      return {
        content: [{ type: "text", text: String(r.rendered ?? JSON.stringify(r)) }],
        details: r
      };
    }
  });
  api.registerTool({
    name: "governance_ledger",
    description: "\u67E5\u8BE2\u5DE5\u7A0B\u6559\u8BAD\u53F0\u8D26\uFF08pvs.gate\uFF09\uFF1A\u4E0D\u5E26 id \u5217\u51FA\u5168\u90E8\uFF1B\u5E26 id \u53D6\u5355\u6761\u516D\u5B57\u6BB5\uFF08\u75C7\u72B6/\u6839\u56E0/\u65AD\u8A00/\u6559\u8BAD/\u9002\u7528\u9762/\u9A8C\u8BC1\uFF09\u3002",
    parameters: Type.Object({ id: Type.Optional(Type.String()) }),
    outputSchema: Type.Object({}, { additionalProperties: true }),
    async execute(_id, params) {
      const args = params?.id ? ["--id", String(params.id)] : [];
      const r = await bridgeCallAsync(cfg, "ledger", args);
      return {
        content: [{ type: "text", text: JSON.stringify(r, null, 1) }],
        details: r
      };
    }
  });
  api.registerTool({
    name: "governance_deposit",
    description: "\u51B3\u7B56\u5165\u8D26\uFF08\u8BB0\u5FC6\u751F\u6B7B\u5C42\uFF09\uFF1A\u63D0\u8BAE\u5E26\u7406\u7531\u3001\u51B3\u8BAE\u5E26\u56E0\u679C\u5165\u8D26\uFF0C\u5165\u8D26\u5373\u539F\u5B50\u843D\u76D8\uFF08\u8FDB\u7A0B\u6B7B\u8BB0\u5FC6\u4E0D\u6B7B\uFF09\u3002\u53EA\u8BB0\u62CD\u677F\u4E0E\u5DF2\u9A8C\u8BC1\u7ED3\u8BBA\uFF0C\u4E0D\u8BB0\u8FC7\u7A0B\u6D41\u6C34\u3002",
    parameters: Type.Object({
      obj: Type.String({ description: "\u5BF9\u8C61/\u4E3B\u9898" }),
      act: Type.String({ description: "\u52A8\u4F5C/\u51B3\u8BAE" }),
      actual: Type.Optional(Type.String({ description: "\u5B9E\u9645\u7ED3\u679C/\u8BC1\u636E" })),
      cur: Type.Optional(Type.String({ description: "\u5F53\u524D\u72B6\u6001/\u53E3\u5F84" }))
    }),
    outputSchema: Type.Object({}, { additionalProperties: true }),
    async execute(_id, params) {
      const args = [
        "--obj",
        String(params.obj),
        "--act",
        String(params.act),
        "--actual",
        String(params.actual ?? ""),
        "--cur",
        String(params.cur ?? "")
      ];
      const r = await bridgeCallAsync(cfg, "deposit", args);
      return {
        content: [{ type: "text", text: `\u5DF2\u5165\u8D26: ${r?.entry?.id ?? "?"}` }],
        details: r
      };
    }
  });
  api.registerTool({
    name: "governance_recall",
    description: "\u7B7E\u540D\u95E8\u63A7\u53EC\u56DE\uFF1Amax(Jaccard, \u67E5\u8BE2\u8986\u76D6\u7387) \u22650.3 \u624D\u51FA\u8D26\uFF0C\u4E2D\u6587\u652F\u6301 bigram \u90E8\u5206\u5339\u914D\uFF0C\u88AB\u53EC\u56DE\u5373\u4FDD\u6D3B\u3002\u627E\u300C\u4E0A\u6B21\u4E3A\u4EC0\u4E48\u8FD9\u4E48\u5B9A\u300D\u7528\u5B83\uFF0C\u522B\u7FFB\u6587\u4EF6\u3002",
    parameters: Type.Object({
      signature: Type.String({ description: "\u67E5\u8BE2\u7B7E\u540D\uFF08\u7A7A\u683C\u5206\u9694\u7684\u8BCD\uFF09" }),
      k: Type.Optional(Type.Number({ description: "\u8FD4\u56DE\u4E0A\u9650\uFF0C\u9ED8\u8BA4 8" }))
    }),
    outputSchema: Type.Object({}, { additionalProperties: true }),
    async execute(_id, params) {
      const args = ["--signature", String(params.signature)];
      if (params.k) args.push("--k", String(Math.floor(Number(params.k))));
      const r = await bridgeCallAsync(cfg, "recall", args);
      return {
        content: [{ type: "text", text: JSON.stringify(r, null, 1) }],
        details: r
      };
    }
  });
}

// src/context-engine.ts
import { delegateCompactionToRuntime } from "openclaw/plugin-sdk/core";
import { readFileSync as readFileSync3, statSync as statSync2 } from "node:fs";

// src/thinking_stub.ts
import { appendFileSync, mkdirSync, readFileSync as readFileSync2, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath as fileURLToPath2 } from "node:url";
var STUB_TEXT = "\uFF08\u5386\u53F2\u601D\u8003\u5DF2\u7701\u7565\uFF09";
var GATE_FILE = fileURLToPath2(new URL("../config/thinking_stub.json", import.meta.url));
var DEFAULT_LOG_DIR = fileURLToPath2(new URL("../../\u8BB0\u5FC6\u4F53/shadow/logs/", import.meta.url));
var __cache = /* @__PURE__ */ new Map();
function stubGate() {
  try {
    const st = statSync(GATE_FILE);
    const hit = __cache.get(GATE_FILE);
    if (hit && hit.mtimeMs === st.mtimeMs && hit.size === st.size) return hit.gate;
    const g = JSON.parse(readFileSync2(GATE_FILE, "utf8"));
    const mode = g?.mode === "shadow" || g?.mode === "on" ? g.mode : "off";
    const gate = {
      mode,
      stubText: typeof g?.stubText === "string" && g.stubText ? g.stubText : STUB_TEXT,
      logDir: typeof g?.logDir === "string" && g.logDir ? g.logDir : DEFAULT_LOG_DIR
    };
    __cache.set(GATE_FILE, { mtimeMs: st.mtimeMs, size: st.size, gate });
    return gate;
  } catch {
    return { mode: "off", stubText: STUB_TEXT, logDir: DEFAULT_LOG_DIR };
  }
}
function scanMessage(m, stubText) {
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
        redacted += 1;
      }
    }
  }
  if (!sawThinkingBlock) {
    const rc = m?.reasoning_content;
    if (typeof rc === "string" && rc && rc !== stubText) chars += rc.length;
  }
  return { chars, hit: chars > 0 ? 1 : 0, redacted };
}
function scanMessages(messages, stubText) {
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
function applyStub(messages, stubText) {
  return (messages ?? []).map((m) => {
    if (String(m?.role ?? "") !== "assistant") return m;
    const content = m?.content;
    if (Array.isArray(content)) {
      let touched = false;
      const next = content.map((b) => {
        if (b && typeof b === "object" && b.type === "thinking") {
          const t = String(b.thinking ?? "");
          if (t && t !== stubText) {
            touched = true;
            return { ...b, thinking: stubText };
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
function shadowLog(gate, sessionKey, scan) {
  if (scan.hitTurns === 0 && scan.thinkChars === 0) return;
  try {
    mkdirSync(gate.logDir, { recursive: true });
    const tok = scan.thinkChars / 3;
    const rec = {
      ts: (/* @__PURE__ */ new Date()).toISOString(),
      session: String(sessionKey ?? ""),
      hit_turns: scan.hitTurns,
      think_chars: scan.thinkChars,
      redacted_skipped: scan.redactedSkipped,
      proj_tok: Math.round(tok),
      proj_yuan_miss: +(tok / 1e6 * 3).toFixed(4),
      // 未命中价口径（上界）
      proj_yuan_cache: +(tok / 1e6 * 0.025).toFixed(4)
      // 缓存命中价口径（下界）
    };
    appendFileSync(join(gate.logDir, "thinking_stub_shadow.jsonl"), JSON.stringify(rec) + "\n");
  } catch {
  }
}

// src/context-engine.ts
import { fileURLToPath as fileURLToPath3 } from "node:url";
var __gateCache = /* @__PURE__ */ new Map();
function __gateFileFor(cfg) {
  if (cfg && typeof cfg.daemonForwardFile === "string" && cfg.daemonForwardFile) {
    return cfg.daemonForwardFile;
  }
  return fileURLToPath3(new URL("../config/daemon_forward.json", import.meta.url));
}
function __loadGate(cfg) {
  const path = __gateFileFor(cfg);
  try {
    const st = statSync2(path);
    const hit = __gateCache.get(path);
    if (hit && hit.mtimeMs === st.mtimeMs && hit.size === st.size) return hit.gate;
    const gate = JSON.parse(readFileSync3(path, "utf8"));
    __gateCache.set(path, { mtimeMs: st.mtimeMs, size: st.size, gate });
    return gate;
  } catch {
    return null;
  }
}
function __forwardEndpoint(gate, sessionKey) {
  if (!gate || !gate.enabled) return null;
  for (const p of gate.sessions ?? []) {
    if (p === "*" || p && sessionKey.startsWith(p)) {
      return (gate.endpoint ?? "http://127.0.0.1:8877").replace(/\/$/, "");
    }
  }
  return null;
}
function estimateTokensForContent(content) {
  if (content == null) return 0;
  const str = typeof content === "string" ? content : JSON.stringify(content);
  let tokens = 0;
  for (let i = 0; i < str.length; i++) {
    const ch = str[i];
    if (ch >= "\u4E00" && ch <= "\u9FFF" || // 中文
    ch >= "\u3040" && ch <= "\u309F" || // 日文平假名
    ch >= "\u30A0" && ch <= "\u30FF" || // 日文片假名
    ch >= "\uAC00" && ch <= "\uD7AF" || // 韩文
    ch >= "\u3400" && ch <= "\u4DBF" || // 中文扩展A
    ch >= "\u20000" && ch <= "\u2A6Df") {
      tokens += 0.8;
    } else {
      tokens += 0.18;
    }
  }
  return Math.ceil(tokens);
}
function sigOf(messages) {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m?.role === "user") {
      let t;
      if (typeof m.content === "string") {
        t = m.content;
      } else if (Array.isArray(m.content)) {
        t = m.content.map((blk) => typeof blk === "string" ? blk : blk?.thinking ?? blk?.text ?? blk?.content ?? "").filter(Boolean).join(" ");
      } else {
        t = JSON.stringify(m.content ?? "");
      }
      return t.slice(0, 300);
    }
  }
  return "";
}
var constraintsCache = null;
async function __constraintsFor(cfg) {
  if (constraintsCache !== null) return constraintsCache || void 0;
  try {
    const r = await bridgeCallAsync(cfg, "constraints");
    const lines = r?.lines ?? [];
    constraintsCache = lines.length ? "## \u6CBB\u7406\u6CBB\u7406\u7EAA\u5F8B\u9762\uFF08\u4E8B\u524D\u7EA6\u675F\xB7\u6559\u8BAD\u65AD\u8A00\u5E38\u9A7B\uFF09\n" + lines.map((l) => `- ${l}`).join("\n") : "";
    return constraintsCache || void 0;
  } catch (e) {
    console.error("[memgate] \u6CBB\u7406\u7EAA\u5F8B\u9762\u83B7\u53D6\u5931\u8D25\uFF08fail-soft \u96F6\u6CE8\u5165\uFF09:", e);
    return void 0;
  }
}
var __ingestedWm = /* @__PURE__ */ new Map();
function __msgKeyOf(m) {
  const role = String(m?.role ?? "?");
  const text = typeof m?.content === "string" ? m.content : JSON.stringify(m?.content ?? "");
  return role + "\0" + text;
}
function __wmFor(sessionId) {
  const key = String(sessionId ?? "_");
  let wm = __ingestedWm.get(key);
  if (!wm) {
    wm = /* @__PURE__ */ new Map();
    __ingestedWm.set(key, wm);
    if (__ingestedWm.size > 200) {
      const first = __ingestedWm.keys().next().value;
      if (first !== void 0) __ingestedWm.delete(first);
    }
  }
  return wm;
}
async function __ingestMessage(cfg, message, wm) {
  const role = String(message?.role ?? "?");
  let text;
  if (typeof message?.content === "string") {
    text = message.content;
  } else if (Array.isArray(message?.content)) {
    text = message.content.map((blk) => {
      if (typeof blk === "string") return blk;
      return blk?.thinking ?? blk?.text ?? blk?.content ?? "";
    }).filter(Boolean).join(" ");
  } else {
    text = JSON.stringify(message?.content ?? "");
  }
  await bridgeCallAsync(cfg, "ingest", ["--role", role, "--text", text.slice(0, 2e3)]);
  if (wm) {
    wm.set(__msgKeyOf(message), true);
    while (wm.size > 6e3) {
      const k = wm.keys().next().value;
      if (k === void 0) break;
      wm.delete(k);
    }
  }
}
var __SUPPLY_BURST = 200;
async function __supplementIngest(cfg, sessionId, messages) {
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
function registerGovernanceContextEngine(api, cfg) {
  api.registerContextEngine("memgate", () => {
    const hotN = cfg.hotWindowMessages ?? 12;
    return {
      info: {
        id: "memgate",
        name: "Governance Middleware Context Engine",
        ownsCompaction: false,
        // 委托模式：压缩零丢失判据通过前不接管
        acceptedHostParams: ["sessionKey", "runtimeContext"],
        transcriptSemantics: {
          currentTurnFence: "before-current-turn-entry-v1",
          turnAdvancementIdempotency: "atomic-idempotent-v1"
        }
      },
      async ingest({ sessionId, message }) {
        await __ingestMessage(cfg, message, __wmFor(sessionId));
        return { ingested: true };
      },
      async assemble({ sessionId, sessionKey, messages, tokenBudget }) {
        await __supplementIngest(cfg, sessionId, messages ?? []);
        const hot = (messages ?? []).slice(-hotN);
        const estimatedTokens = estimateTokensForContent(hot);
        const parts = [];
        const ban = await __constraintsFor(cfg);
        if (ban) parts.push(ban);
        try {
          const ess = await bridgeCallAsync(cfg, "recall", [
            "--signature",
            "\u6559\u8BAD|\u94C1\u5F8B|\u4E8B\u6545|\u6839\u56E0|\u7981\u6B62|\u62CD\u677F",
            "--k",
            "8"
          ]);
          const essHits = ess?.hits ?? [];
          if (essHits.length > 0) {
            parts.push(
              "## \u5386\u53F2\u6559\u8BAD\u63D0\u9192\uFF08\u6559\u8BAD\u4F18\u5148\xB7\u81EA\u52A8\u6CE8\u5165\uFF09\n" + essHits.map((h, i) => `${i + 1}. ${h.entry?.signature ?? "?"}`).join("\n")
            );
          }
        } catch {
        }
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
                session: sk,
                signature: sigOf(messages ?? []),
                k: 6,
                messages: (messages ?? []).slice(-200),
                total_messages: (messages ?? []).length
              }),
              signal: AbortSignal.timeout(gate?.timeoutMs ?? 2500)
            });
            const rd = await resp.json();
            if (!rd?.ok || !Array.isArray(rd.hits)) {
              throw new Error(`daemon decision bad payload: ${resp.status}`);
            }
            const hits = rd.hits;
            if (hits.length) {
              parts.push(
                "## \u51B3\u7B56\u8BB0\u5FC6\u53EC\u56DE\uFF08\u6E29\u5C42\xB7\u7B7E\u540D\u95E8\u63A7\uFF09\n" + hits.map((h) => `- ${h.entry?.signature ?? "?"}\uFF08\u76F8\u4F3C\u5EA6 ${h.score}\uFF09`).join("\n")
              );
            }
            decided = true;
          } catch (e) {
            console.error("[memgate] \u8F6C\u63A5\u5931\u8D25\uFF08fail-soft \u56DE\u9000\u539F\u8DEF\u5F84\uFF09:", e);
          }
        }
        if (!decided) {
          try {
            const r = await bridgeCallAsync(cfg, "recall", [
              "--signature",
              sigOf(messages ?? []),
              "--k",
              "6"
            ]);
            const hits = r?.hits ?? [];
            if (hits.length) {
              parts.push(
                "## \u51B3\u7B56\u8BB0\u5FC6\u53EC\u56DE\uFF08\u6E29\u5C42\xB7\u7B7E\u540D\u95E8\u63A7\uFF09\n" + hits.map((h) => `- ${h.entry?.signature ?? "?"}\uFF08\u76F8\u4F3C\u5EA6 ${h.score}\uFF09`).join("\n")
              );
            }
          } catch (e) {
            console.error("[memgate] \u6E29\u5C42\u53EC\u56DE\u5931\u8D25\uFF08fail-soft \u96F6\u6CE8\u5165\uFF09:", e);
          }
        }
        void tokenBudget;
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
          systemPromptAddition: parts.length ? parts.join("\n\n") : void 0
        };
      },
      async compact(params) {
        return await delegateCompactionToRuntime(params);
      },
      async commitTurn({ advancementKey, messages }) {
        const payload = JSON.stringify(messages ?? []).slice(0, 200);
        const r = await bridgeCallAsync(cfg, "commit", [
          "--key",
          String(advancementKey),
          "--payload",
          payload
        ]);
        return { status: r.status === "duplicate" ? "duplicate" : "committed" };
      }
    };
  });
}

// src/memory-capability.ts
function registerGovernanceMemory(api, cfg) {
  api.registerMemoryCapability({
    // 确定性召回工具由本插件的 governance_recall 提供（provider 直查的落点）
    deterministicRecallToolName: "governance_recall",
    promptBuilder: (params) => {
      void params;
      try {
        const r = bridgeCall(cfg, "digest", ["--k", "8"]);
        const top = r?.top ?? [];
        if (!top.length) return [];
        const lines = top.map(
          (e) => `- ${e.signature ?? "?"}\uFF08hits=${e.hits}\uFF0C${e.ts ?? "?"}\uFF09`
        );
        return [
          "## \u51B3\u7B56\u8BB0\u5FC6\uFF08\u6E29\u5C42\xB7\u8D26\u672C\u6458\u8981\uFF09\n" + lines.join("\n") + "\n\uFF08\u68C0\u7D22\uFF1Agovernance_recall \u5DE5\u5177\uFF1B\u5165\u8D26\uFF1Agovernance_deposit\uFF09"
        ];
      } catch (e) {
        console.error("[memgate] \u8BB0\u5FC6\u6458\u8981\u5931\u8D25\uFF08fail-soft \u96F6\u6CE8\u5165\uFF09:", e);
        return [];
      }
    }
  });
}

// src/toolface_hook.ts
import { readFileSync as readFileSync4 } from "node:fs";
import { fileURLToPath as fileURLToPath4 } from "node:url";
var GATE_CFG2 = fileURLToPath4(new URL("../config/daemon_forward.json", import.meta.url));
var faceCache = /* @__PURE__ */ new Map();
function gateState() {
  try {
    const g = JSON.parse(readFileSync4(GATE_CFG2, "utf-8"));
    return {
      on: !!g.toolfaceHook,
      endpoint: typeof g.endpoint === "string" ? g.endpoint : "http://127.0.0.1:8877"
    };
  } catch {
    return { on: false, endpoint: "http://127.0.0.1:8877" };
  }
}
function jaccard(a, b) {
  const ta = new Set(a.split(/\s+/).filter(Boolean));
  const tb = new Set(b.split(/\s+/).filter(Boolean));
  if (!ta.size || !tb.size) return 0;
  let inter = 0;
  for (const t of ta) if (tb.has(t)) inter++;
  return inter / (ta.size + tb.size - inter);
}
function registerToolfaceHook(api, _cfg) {
  api.on(
    "before_prompt_build",
    async (event, ctx) => {
      const gate = gateState();
      if (!gate.on) return;
      const sig = String(event?.prompt ?? "").slice(0, 4e3);
      const sid = String(ctx?.sessionId ?? ctx?.sessionKey ?? "default");
      const cached = faceCache.get(sid);
      if (cached && jaccard(sig, cached.sig) >= 0.3) return { toolsAllow: cached.face };
      const ac = new AbortController();
      const timer = setTimeout(() => ac.abort(), 400);
      try {
        const res = await fetch(gate.endpoint.replace(/\/$/, "") + "/toolface", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ signature: sig }),
          signal: ac.signal
        });
        const body = await res.json();
        const face = body?.projected;
        if (!res.ok || !Array.isArray(face) || face.length === 0) return;
        if (faceCache.size > 200) faceCache.clear();
        faceCache.set(sid, { face, sig });
        return { toolsAllow: face };
      } catch {
        return;
      } finally {
        clearTimeout(timer);
      }
    }
  );
}

// index.ts
var index_default = definePluginEntry({
  id: "memgate",
  name: "MemGate",
  description: "Three-layer memory (hot/warm/cold) + governance gate tools, bridged to the Python single-source.",
  register(api) {
    const cfg = api.pluginConfig ?? {};
    registerGovernanceTools(api, cfg);
    registerGovernanceContextEngine(api, cfg);
    registerGovernanceMemory(api, cfg);
    registerToolfaceHook(api, cfg);
  }
});
export {
  index_default as default
};
