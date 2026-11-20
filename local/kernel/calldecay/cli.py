# -*- coding: utf-8 -*-
"""calldecay 命令行：serve（代理）/ demo（离线演示）。"""

import argparse
import json
import os


def _parse_upstreams(items):
    """--upstream 可重复：name=URL 或裸 URL（记名 default）；首项=主上游。"""
    ups = {}
    for item in items or []:
        if item.startswith("http://") or item.startswith("https://"):
            name, url = "default", item
        else:
            name, sep, url = item.partition("=")
            if not sep:
                name, url = "default", item
        ups[name] = url
    return ups


def cmd_serve(args):
    ups = _parse_upstreams(args.upstream)
    if ups:
        chain = list(ups.values())
        primary = chain[0]
        os.environ["LLM_ARM_HOSTS"] = ",".join(chain)   # 窄接口同链回落
    else:
        primary = "http://127.0.0.1:8082"
    os.environ.setdefault("LLM_ARM", "1")
    os.environ["LLM_ARM_HOST"] = primary
    os.environ.setdefault("LLM_ARM_CHAT", "1")
    os.environ.setdefault("LLM_ARM_AUDIT_DIR", "/tmp/calldecay_audit")
    if args.model:
        os.environ.setdefault("LLM_ARM_MODEL", args.model)
    from .proxy import serve
    serve(listen=args.listen, upstream=primary, model=args.model,
          upstreams=ups or None)


def cmd_demo(args):
    from . import mock as mockmod
    host, port, _srv = mockmod.start_mock_server()
    os.environ["LLM_ARM"] = "1"
    os.environ["LLM_ARM_HOST"] = f"http://{host}:{port}"
    os.environ["LLM_ARM_CHAT"] = "1"
    os.environ.setdefault("LLM_ARM_AUDIT_DIR", "/tmp/calldecay_audit")
    from .adapter import CallDecay
    cd = CallDecay()
    print("== CallDecay 离线演示（mock LLM）==")
    acts = ["喂食", "放牧", "观望", "保护"]
    for step in range(1, 9):
        d = cd.decide(obj="兔", goal="丰", current="兔", actions=acts)
        mark = "   <- 命中查表=0 上游调用" if d["source"] == "table" else ""
        print(f"第 {step} 步: act={d['act']}  source={d['source']}{mark}")
        cd.learn(obj="兔", act=d["act"], actual="丰", cur="兔")
    print("指标:", json.dumps(cd.metrics.summary(), ensure_ascii=False))


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="calldecay", description="CallDecay —— 决策记忆中间件")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="启动 OpenAI 兼容代理（改 base_url 即接）")
    s.add_argument("--listen", default="127.0.0.1:8787")
    s.add_argument("--upstream", action="append", default=None,
                   metavar="NAME=URL",
                   help="上游 OpenAI 兼容端点，可重复：local=URL cloud=URL（声明序=回落序；"
                        "首项为主上游；裸 URL 记名 default）")
    s.add_argument("--model", default="calldecay-decided")
    s.set_defaults(func=cmd_serve)
    d = sub.add_parser("demo", help="离线演示（内置 mock LLM，3 分钟看懂）")
    d.set_defaults(func=cmd_demo)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
