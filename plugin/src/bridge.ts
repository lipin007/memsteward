// bridge.ts — TS→Python 唯一桥客户端（业务逻辑单源在 Python，本层零业务逻辑）
// 形状钉自 openclaw 2026.9.4；双通道：
//   bridgeCall      同步单发（--oneshot）：请求载荷经 stdin 传 JSON
//                   ——execve 单参上限（MAX_ARG_STRLEN≈128KiB）整类绕开，旧 ARG_CAP 截断已删
//   bridgeCallAsync 常驻 worker（--serve）：逐行 JSON-RPC over stdio，进程复用＋崩溃自愈
// 业务帽仍在 Python 侧（ingest 存储 ≤200 字符）；TS 不做业务截断。
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export interface BridgeConfig {
  pythonBin?: string;
  bridgePath?: string;
  landingPath?: string;
  workspaceRoot?: string;
  hotWindowMessages?: number;
  coldStartTokenBudget?: number;
  /** S2 远程桥（2026-11-10 拍板「2切换」）：显式守护端点；缺省时读 config/daemon_forward.json
   *  的 bridgeRemote+endpoint。命中走守护 /bridge，失败 fail-soft 回落本地 worker（零中断）。 */
  remoteEndpoint?: string;
  remoteBridge?: boolean;
}

const DEFAULT_BRIDGE = fileURLToPath(new URL("./bridge_cli.py", import.meta.url));

function flagTail(cfg: BridgeConfig, args: string[]): string[] {
  const tail: string[] = [];
  if (cfg.landingPath) tail.push("--landing", cfg.landingPath);
  if (cfg.workspaceRoot) tail.push("--ws", cfg.workspaceRoot);
  return tail.concat(args.map(String));
}

/** 同步调 Python 桥（--oneshot）：返回解析后 JSON。失败抛错（写路径由调用方定 fail 语义）。 */
export function bridgeCall(cfg: BridgeConfig, sub: string, args: string[] = []): any {
  const bin = cfg.pythonBin ?? "python3";
  const bridge = cfg.bridgePath ?? DEFAULT_BRIDGE;
  const out = execFileSync(bin, [bridge, "--oneshot"], {
    input: JSON.stringify({ sub, args: flagTail(cfg, args) }),
    encoding: "utf-8",
    timeout: 5_000,  // 同步面仅 promptBuilder（实测 warm 10–20ms ⇒ 250×余量）；python 挂死最坏卡事件循环 5s 而非 30s，保登录页可用
    maxBuffer: 8 * 1024 * 1024,
  });
  return JSON.parse(out);
}

// ── 常驻 worker（--serve）────────────────────────────────────────────────
interface Pending {
  resolve: (v: any) => void;
  reject: (e: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

class BridgeWorker {
  private proc: ChildProcess | null = null;
  private nextId = 1;
  private pending = new Map<number, Pending>();
  private buf = "";
  constructor(private readonly cfg: BridgeConfig) {}

  private ensure(): ChildProcess {
    if (this.proc && this.proc.exitCode === null) return this.proc;
    const bin = this.cfg.pythonBin ?? "python3";
    const bridge = this.cfg.bridgePath ?? DEFAULT_BRIDGE;
    const proc = spawn(bin, [bridge, "--serve"], { stdio: ["pipe", "pipe", "pipe"] });
    this.buf = "";
    proc.stdout!.on("data", (d: Buffer) => this.onData(d));
    proc.stderr!.on("data", (d: Buffer) => {
      const s = d.toString().trim();
      if (s) console.error("[memgate] worker stderr:", s.slice(0, 500));
    });
    proc.on("exit", () => this.onExit(proc));
    proc.on("error", (err) => this.onError(proc, err));
    this.proc = proc;
    return proc;
  }

  private onData(d: Buffer): void {
    this.buf += d.toString("utf-8");
    let nl: number;
    while ((nl = this.buf.indexOf("\n")) >= 0) {
      const line = this.buf.slice(0, nl).trim();
      this.buf = this.buf.slice(nl + 1);
      if (!line) continue;
      let msg: any;
      try { msg = JSON.parse(line); } catch { continue; }
      const p = this.pending.get(msg.id);
      if (!p) continue;
      this.pending.delete(msg.id);
      clearTimeout(p.timer);
      if (msg.ok) p.resolve(msg.result);
      else p.reject(new Error(String(msg.error ?? "bridge worker error")));
    }
  }

  private onExit(proc: ChildProcess): void {
    if (this.proc === proc) this.proc = null;
    for (const [, p] of this.pending) {
      clearTimeout(p.timer);
      p.reject(new Error("bridge worker exited"));
    }
    this.pending.clear();
  }

  private onError(proc: ChildProcess, err: Error): void {
    if (this.proc === proc) this.proc = null;
    for (const [, p] of this.pending) {
      clearTimeout(p.timer);
      p.reject(new Error(`bridge worker spawn: ${err.message}`));
    }
    this.pending.clear();
  }

  call(sub: string, tail: string[]): Promise<any> {
    return new Promise((resolve, reject) => {
      const proc = this.ensure();
      const id = this.nextId++;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        this.dispose();
        reject(new Error(`bridge worker timeout: ${sub}`));
      }, 30_000);
      this.pending.set(id, { resolve, reject, timer });
      proc.stdin!.write(JSON.stringify({ id, sub, args: tail }) + "\n", (err) => {
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

  dispose(): void {
    const proc = this.proc;
    this.proc = null;
    for (const [, p] of this.pending) {
      clearTimeout(p.timer);
      p.reject(new Error("bridge worker disposed"));
    }
    this.pending.clear();
    if (proc && proc.exitCode === null) proc.kill("SIGTERM");
  }
}

const GATE_CFG = fileURLToPath(new URL("../config/daemon_forward.json", import.meta.url));

function remoteFor(cfg: BridgeConfig): string | null {
  // 显式 opt-out（remoteBridge:false）压过 gate 文件——测试/旁路场景强制本地路径
  if (cfg.remoteBridge === false) return null;
  if (cfg.remoteEndpoint) return cfg.remoteEndpoint;
  try {
    const g = JSON.parse(readFileSync(GATE_CFG, "utf-8"));
    if (g && g.bridgeRemote && typeof g.endpoint === "string") return g.endpoint;
  } catch { /* 无 gate 文件＝原路径 */ }
  return null;
}

async function remoteCall(endpoint: string, sub: string, tail: string[]): Promise<any> {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 25_000);
  try {
    const res = await fetch(endpoint.replace(/\/$/, "") + "/bridge", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sub, args: tail }),
      signal: ac.signal,
    });
    const body = await res.json();
    if (!res.ok || (body && body.ok === false && body.error)) {
      throw new Error(String(body?.error ?? `HTTP ${res.status}`));
    }
    // 形状契约对齐（2026-11-12 修复）：守护 /bridge 回的是 worker 信封
    // {id,ok,result}，而本地 worker 路径 resolve 的是 msg.result——双通道
    // 必须同形。旧代码把信封原样上抛：工具层 details.entry/引擎 r.hits 全
    // 空、commit 幂等口把 duplicate 显示成 committed（daemon 在跑即触发，
    // daemon 死走 worker 兜底反而正常 ⇒ 长期潜伏）。裸结果无 "result" 键
    // 原样返回（preflight 顶层自带 ok 字段——不可用 ok 判信封，只认键）。
    return (body && typeof body === "object" && body.ok === true && "result" in body)
      ? body.result : body;
  } finally { clearTimeout(timer); }
}

const workers = new Map<string, BridgeWorker>();

function workerFor(cfg: BridgeConfig): BridgeWorker {
  const key = `${cfg.pythonBin ?? "python3"}|${cfg.bridgePath ?? DEFAULT_BRIDGE}`;
  let w = workers.get(key);
  if (!w) {
    w = new BridgeWorker(cfg);
    workers.set(key, w);
  }
  return w;
}

/** 异步调 Python 桥（常驻 worker）：进程复用，崩溃后下次调用自动重建。失败抛错。
 *  S2 远程桥命中时先走守护 /bridge，失败 fail-soft 回落本地 worker。 */
export function bridgeCallAsync(cfg: BridgeConfig, sub: string, args: string[] = []): Promise<any> {
  const tail = flagTail(cfg, args);
  const ep = remoteFor(cfg);
  if (ep) return remoteCall(ep, sub, tail).catch(() => workerFor(cfg).call(sub, tail));
  return workerFor(cfg).call(sub, tail);
}
