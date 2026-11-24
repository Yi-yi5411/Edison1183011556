# -*- coding: utf-8 -*-
"""临时验证：DSH 内核 MCP 工具调用链路分层测试。

L1 直连 mcp_server.py：initialize → tools/list（109）→ tools/call health
L2 DSH ACP：initialize → session/new（挂载 MCP）
L3 端到端读工具：prompt 触发 tool_call → completed
L4 端到端写工具 + 权限确认：prompt → session/request_permission → allow → 执行
"""
import asyncio, json, os, sys

ROOT = r"C:\Users\Administrator\Desktop\structural_inspection"
CLI = os.path.join(ROOT, "data", "dsh_runtime", "app", "dsh", "node_modules",
                   "@deepseek-ai", "dsh-desktop-host", "lib", "cli.js")
NODE = r"D:\新建文件夹\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
PYTHON = r"C:\Program Files\python\python.exe"
MCP = os.path.join(ROOT, "webapp", "mcp_server.py")

verdicts = []

def verdict(name, passed, detail=""):
    verdicts.append((name, passed, detail))
    print(("PASS " if passed else "FAIL ") + name + ("  | " + detail if detail else ""))

# ── L1：直连 MCP server ──────────────────────────────────────
async def layer1():
    proc = await asyncio.create_subprocess_exec(
        PYTHON, "-u", MCP,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
             "STRUCTURAL_API_BASE": "http://127.0.0.1:8765/api"})
    pending = {}

    async def reader():
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode("utf-8", "replace"))
            except Exception:
                continue
            fut = pending.pop(msg.get("id"), None)
            if fut and not fut.done():
                fut.set_result(msg)

    rt = asyncio.create_task(reader())
    asyncio.create_task(_drain(proc.stderr))

    async def req(i, method, params, timeout=30):
        fut = asyncio.get_running_loop().create_future()
        pending[i] = fut
        proc.stdin.write((json.dumps({"jsonrpc": "2.0", "id": i, "method": method,
                                      "params": params}) + "\n").encode())
        await proc.stdin.drain()
        return await asyncio.wait_for(fut, timeout)

    try:
        r = await req(1, "initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "chain-verify", "version": "0.0.1"}})
        proc.stdin.write((json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode())
        await proc.stdin.drain()
        ok_init = "serverInfo" in (r.get("result") or {})
        r = await req(2, "tools/list", {})
        tools = [t.get("name") for t in (r.get("result") or {}).get("tools") or []]
        verdict("L1a MCP initialize", ok_init,
                str((r.get("result") or {}).get("serverInfo", {})))
        verdict("L1b tools/list 数量", len(tools) == 109, "%d 个工具" % len(tools))
        r = await req(3, "tools/call", {"name": "health", "arguments": {}})
        text = "".join(c.get("text", "") for c in ((r.get("result") or {}).get("content") or []))
        passed = any(k in text.lower() for k in ("ok", "true", "running", "version")) or "运行" in text
        verdict("L1c tools/call health", passed, text[:150])
    except Exception as exc:
        verdict("L1 直连 MCP", False, repr(exc)[:200])
    finally:
        try:
            proc.kill()
        except Exception:
            pass

async def _drain(stream):
    while True:
        line = await stream.readline()
        if not line:
            return
        sys.stderr.write("[dsh] " + line.decode("utf-8", "replace"))

# ── L2-L4：DSH ACP 端到端 ────────────────────────────────────
async def layer_acp():
    env = {**os.environ, "ELECTRON_RUN_AS_NODE": "1",
           "OLLAMA_API_KEY": "ollama", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    proc = await asyncio.create_subprocess_exec(
        NODE, CLI, "--profile", "acp",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, cwd=ROOT, env=env)
    pending = {}
    tool_events = []      # (toolCallId, title, status)
    permissions_seen = []
    session_id_box = {}

    async def reader():
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode("utf-8", "replace"))
            except Exception:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                fut = pending.pop(int(msg["id"]), None)
                if fut and not fut.done():
                    fut.set_result(msg if "error" in msg else msg.get("result"))
                continue
            method = msg.get("method", "")
            params = msg.get("params") or {}
            if method == "session/update":
                upd = params.get("update") or {}
                kind = upd.get("sessionUpdate")
                if kind in ("tool_call", "tool_call_update"):
                    tool_events.append((upd.get("toolCallId"), upd.get("title"), upd.get("status")))
            elif method == "session/request_permission":
                options = params.get("options") or []
                allow = next((o for o in options if str(o.get("kind", "")).startswith("allow")), None)
                option_id = (allow or {}).get("optionId") or (options or [{}])[0].get("optionId")
                permissions_seen.append([o.get("kind") for o in options])
                await reply(msg["id"], {"outcome": {"outcome": "selected", "optionId": option_id}})

    async def reply(rid, result):
        proc.stdin.write((json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}) + "\n").encode())
        await proc.stdin.drain()

    rt = asyncio.create_task(reader())
    asyncio.create_task(_drain(proc.stderr))

    async def req(i, method, params, timeout=120):
        fut = asyncio.get_running_loop().create_future()
        pending[i] = fut
        proc.stdin.write((json.dumps({"jsonrpc": "2.0", "id": i, "method": method,
                                      "params": params}) + "\n").encode())
        await proc.stdin.drain()
        return await asyncio.wait_for(fut, timeout)

    mcp_servers = [{"name": "structural_inspection", "command": PYTHON, "args": ["-u", MCP],
                    "env": [{"name": "PYTHONIOENCODING", "value": "utf-8"},
                            {"name": "PYTHONUTF8", "value": "1"},
                            {"name": "STRUCTURAL_API_BASE", "value": "http://127.0.0.1:8765/api"}]}]
    try:
        r = await req(1, "initialize", {"protocolVersion": 1, "clientCapabilities": {}}, 60)
        verdict("L2a ACP initialize", isinstance(r, dict) and "agentInfo" in r,
                str((r or {}).get("agentInfo", "")))
        r = await req(2, "session/new", {"cwd": ROOT, "mcpServers": mcp_servers}, 120)
        sid = (r or {}).get("sessionId") if isinstance(r, dict) else None
        session_id_box["sid"] = sid
        verdict("L2b session/new（挂载 MCP）", bool(sid), "sessionId=" + str(sid)[:8])
        if not sid:
            return

        async def prompt(text, timeout=300):
            n = len(tool_events)
            r = await req(3, "session/prompt",
                          {"sessionId": sid, "prompt": [{"type": "text", "text": text}]}, timeout)
            if isinstance(r, dict) and "error" in r:
                return None, r.get("error")
            return (r or {}).get("stopReason"), None

        # L3 读工具
        stop, err = await prompt("请调用 health 工具，然后告诉我返回结果。")
        read_calls = [(t, s) for (tid, t, s) in tool_events]
        completed = [s for (tid, t, s) in tool_events if s == "completed"]
        verdict("L3 读工具端到端（health）",
                bool(completed) and stop == "end_turn" and not err,
                "工具事件=%d, completed=%d, stopReason=%s%s" % (
                    len(read_calls), len(completed), stop, " err=" + str(err) if err else ""))

        # L4 写工具 + 权限确认
        before = len(tool_events)
        stop, err = await prompt("请调用 save_project 工具保存当前工程。")
        write_events = tool_events[before:]
        write_completed = [s for (tid, t, s) in write_events if s == "completed"]
        verdict("L4 写工具+权限确认（save_project）",
                bool(write_completed) and bool(permissions_seen),
                "权限请求=%d 次(选项=%s), completed=%d, stopReason=%s%s" % (
                    len(permissions_seen), permissions_seen, len(write_completed), stop,
                    " err=" + str(err) if err else ""))
    except Exception as exc:
        verdict("L2-L4 ACP 端到端", False, repr(exc)[:300])
    finally:
        try:
            proc.kill()
        except Exception:
            pass

async def main():
    print("=== DSH 内核 MCP 工具链路分层验证 ===")
    if "--l1" not in sys.argv and "--acp" not in sys.argv:
        await layer1()
    if "--l1" not in sys.argv:
        print("---")
        await layer_acp()
    failed = [v for v in verdicts if not v[1]]
    print("总结: %d/%d 通过" % (len(verdicts) - len(failed), len(verdicts)))
    sys.exit(1 if failed else 0)

asyncio.run(main())
