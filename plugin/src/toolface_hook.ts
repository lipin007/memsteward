// toolface_hook.ts — P4 动态工具面接线（before_prompt_build 钩子）2026-11-10 拍板激活
// 设计=P4验收报告 §3.4/3.5：hook → daemon tool_router 投影 → toolsAllow；
// 换脸节奏=分段换脸（任务域内复用缓存脸、域漂移才重投影——缓存经济学定案）；
// 回退=钩子返回 undefined 一行（gate.toolfaceHook:false 即时回天花板，纯放宽无反向风险）；
// fail-soft=daemon 死/超时/坏响应一律返回 undefined（本轮不改，回退现状）。
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core";

const GATE_CFG = fileURLToPath(new URL("../config/daemon_forward.json", import.meta.url));

interface FaceCacheEntry { face: string[]; sig: string }
const faceCache = new Map<string, FaceCacheEntry>();

function gateState(): { on: boolean; endpoint: string } {
  try {
    const g = JSON.parse(readFileSync(GATE_CFG, "utf-8"));
    return {
      on: !!g.toolfaceHook,
      endpoint: typeof g.endpoint === "string" ? g.endpoint : "http://127.0.0.1:8877",
    };
  } catch {
    return { on: false, endpoint: "http://127.0.0.1:8877" };
  }
}

function jaccard(a: string, b: string): number {
  const ta = new Set(a.split(/\s+/).filter(Boolean));
  const tb = new Set(b.split(/\s+/).filter(Boolean));
  if (!ta.size || !tb.size) return 0;
  let inter = 0;
  for (const t of ta) if (tb.has(t)) inter++;
  return inter / (ta.size + tb.size - inter);
}

export function registerToolfaceHook(api: OpenClawPluginApi, _cfg: unknown): void {
  (api as any).on(
    "before_prompt_build",
    async (event: { prompt?: string }, ctx: { sessionId?: string; sessionKey?: string }) => {
      const gate = gateState();
      if (!gate.on) return; // 默认关＝零行为变化；回退开关就这一行的语义
      const sig = String(event?.prompt ?? "").slice(0, 4000);
      const sid = String(ctx?.sessionId ?? ctx?.sessionKey ?? "default");
      // 分段换脸（§3.5）：任务域内复用缓存脸（保住前缀缓存），域漂移才重投影
      const cached = faceCache.get(sid);
      if (cached && jaccard(sig, cached.sig) >= 0.3) return { toolsAllow: cached.face };
      const ac = new AbortController();
      const timer = setTimeout(() => ac.abort(), 400);
      try {
        const res = await fetch(gate.endpoint.replace(/\/$/, "") + "/toolface", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ signature: sig }),
          signal: ac.signal,
        });
        const body = await res.json();
        const face: unknown = body?.projected;
        if (!res.ok || !Array.isArray(face) || face.length === 0) return; // fail-soft
        if (faceCache.size > 200) faceCache.clear();
        faceCache.set(sid, { face: face as string[], sig });
        return { toolsAllow: face as string[] };
      } catch {
        return; // fail-soft：daemon 死/超时＝本轮不改
      } finally {
        clearTimeout(timer);
      }
    },
  );
}
