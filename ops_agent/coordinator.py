"""ops-orchestrator coordinator — on-demand CLI agent.

    python -m ops_agent.coordinator "add an A record dns.lab -> 10.0.0.5"

The four cost levers (see README):
  1. Skills load on demand     -> the load_skill tool injects SKILL.md only when needed
  2. Tools defer + search      -> MCP tools marked defer_loading; surfaced via tool search
  3. Prompt caching            -> cache_control on the stable system prefix
  4. Model tiering             -> coordinator model from config (Sonnet); workers (Haiku) in v1

v0: written to the current API surface; run it and iterate on any SDK-version errors.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .commands import expand_command, help_text, load_commands, parse_command_line
from .router import ModelRouter
from .skills import load_skills, registry_block
from .worker import is_delegatable
from .worker import run as worker_run

ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    cfg_path = ROOT / "config.yaml"
    if not cfg_path.exists():
        cfg_path = ROOT / "config.example.yaml"
    return yaml.safe_load(cfg_path.read_text())


SYSTEM = """You are the ops-orchestrator: a careful infrastructure operator for a homelab.

Work the task in small steps. When a task matches a skill, call load_skill to read its
procedure before acting. Discover infrastructure tools with the tool search before using
them — they are not all loaded up front to save cost. Confirm before any destructive or
hard-to-reverse action (deleting, overwriting, restarting a live service). Report what you
did plainly; if something failed, say so with the error.
"""


READONLY_PREFIXES = ("list", "get", "status", "show", "describe",
                     "find", "search", "read", "check", "lookup")


def _tool_mutating(tool) -> bool:
    """Decide if an MCP tool changes state. Prefer the MCP annotations; fall back to the verb."""
    ann = getattr(tool, "annotations", None)
    if ann is not None:
        if getattr(ann, "readOnlyHint", None) is True:
            return False
        if getattr(ann, "destructiveHint", None) is True:
            return True
    return not tool.name.lower().startswith(READONLY_PREFIXES)


def _confirm(name: str, args: dict, auto_yes: bool = False) -> bool:
    print(f"\n⚠️  MUTATING action requested: {name}\n    args: {json.dumps(args)}", file=sys.stderr)
    if auto_yes:
        print("    [--yes] auto-approved", file=sys.stderr)
        return True
    try:
        return input("    Proceed? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False   # non-interactive without --yes: deny by default


async def main(task: str, force_claude: bool = False, auto_yes: bool = False) -> None:
    cfg = load_config()
    skills = load_skills(ROOT / cfg.get("skills_dir", "skills"))
    router = ModelRouter(cfg)
    if force_claude:
        router.ollama_url = ""   # empty URL will fail immediately -> always fallback to Claude
    defer = bool(cfg.get("defer_tools", False))  # scale lever: only wins with many tools
    confirm_destructive = bool(cfg.get("confirm_destructive", True))

    async with AsyncExitStack() as stack:
        # 1) connect to each local MCP server (creds stay on this host)
        sessions: dict[str, ClientSession] = {}
        tool_owner: dict[str, tuple[str, str]] = {}   # api_name -> (server, real_tool_name)
        tool_mutating: dict[str, bool] = {}           # api_name -> needs confirmation
        tools: list[dict] = []

        for srv in cfg.get("mcp_servers", []):
            cmd = list(srv["command"])
            if cmd and cmd[0] == "python":
                cmd[0] = sys.executable   # use the same interpreter (venv-safe)
            params = StdioServerParameters(
                command=cmd[0],
                args=cmd[1:],
                env={**os.environ, **{str(k): str(v) for k, v in srv.get("env", {}).items()}},
            )
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            sessions[srv["name"]] = session
            for t in (await session.list_tools()).tools:
                api_name = f"{srv['name']}__{t.name}"
                tool_owner[api_name] = (srv["name"], t.name)
                tool_mutating[api_name] = _tool_mutating(t)
                td = {
                    "name": api_name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema,
                }
                # note: defer flag is applied after auto-check below
                tools.append(td)

        # auto-enable defer_tools if tool count exceeds threshold
        auto_defer_threshold = cfg.get("auto_defer_tool_count", 0)
        if auto_defer_threshold and len(tools) >= auto_defer_threshold and not cfg.get("defer_tools"):
            defer = True
            print(f"[router] auto-enabling defer_tools: {len(tools)} tools >= {auto_defer_threshold} threshold",
                  file=sys.stderr)

        # apply defer_loading to MCP tools if defer is enabled
        if defer:
            for td in tools:
                if "__" in td["name"]:  # MCP tools have "server__toolname" format
                    td["defer_loading"] = True

        # 2) local tool: progressive disclosure of skills (never deferred — core + cheap)
        tools.append({
            "name": "load_skill",
            "description": "Load the full procedure for a named skill before acting on it.",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string", "enum": list(skills)}},
                "required": ["name"],
            },
        })
        # 3) tool search so the deferred infra tools can be surfaced on demand
        if defer and tools:
            tools.append({"type": "tool_search_tool_bm25_20251119", "name": "tool_search_tool_bm25"})

        system = [{
            "type": "text",
            "text": SYSTEM + "\n\n" + registry_block(skills),
            "cache_control": {"type": "ephemeral"},   # lever 3: cache the stable prefix
        }]
        messages = [{"role": "user", "content": task}]
        usage = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}

        def log_usage(resp) -> None:
            u = resp.usage
            usage["in"] += u.get("in", 0)
            usage["out"] += u.get("out", 0)
            usage["cache_read"] += u.get("cache_read", 0)
            usage["cache_write"] += u.get("cache_write", 0)
            print(f"  [turn] model={resp.model_used} in={u.get('in',0)} "
                  f"out={u.get('out',0)} cache_read={u.get('cache_read',0)}", file=sys.stderr)

        def summary() -> None:
            # only Claude turns cost money
            cost = (usage["in"] * 3 + usage["cache_read"] * 0.3 + usage["cache_write"] * 3.75
                    + usage["out"] * 15) / 1_000_000
            print(f"\n[total] {router.summary()} | claude cost ~${cost:.5f}", file=sys.stderr)

        # 4) manual agentic loop
        for _ in range(40):
            resp = await asyncio.to_thread(
                router.create,
                system=system, tools=tools, messages=messages, max_tokens=8000,
            )
            log_usage(resp)
            if resp.stop_reason in ("end_turn", "refusal"):
                print("\n".join(b.text for b in resp.content if b.type == "text"))
                if resp.stop_reason == "refusal":
                    print("[refused]")
                summary()
                return
            if resp.stop_reason == "pause_turn":   # server tool (tool search) still working
                messages.append({"role": "assistant", "content": resp.content})
                continue

            # convert Block dataclasses -> plain dicts for the next API call
            def _serialise(b):
                if b.type == "text":
                    return {"type": "text", "text": b.text}
                return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
            messages.append({"role": "assistant", "content": [_serialise(b) for b in resp.content]})
            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                if block.name == "load_skill":
                    skill = skills.get(block.input["name"])
                    out = skill.body if skill else f"unknown skill: {block.input.get('name')}"
                else:
                    server, real = tool_owner[block.name]
                    if confirm_destructive and tool_mutating.get(block.name):
                        if not await asyncio.to_thread(_confirm, block.name, block.input, auto_yes):
                            results.append({"type": "tool_result", "tool_use_id": block.id,
                                            "content": "Operator DECLINED this action. Do not retry it; "
                                                       "pick a different approach or ask what to do."})
                            continue
                    r = await sessions[server].call_tool(real, block.input)
                    out = "\n".join(getattr(c, "text", str(c)) for c in r.content)
                    # worker compression: if this was a Claude turn (costs money),
                    # the result is long, and the tool is read-only — summarise
                    # via Haiku before feeding back into the coordinator's context.
                    worker_model = cfg["models"].get("worker", "")
                    if (worker_model
                            and resp.model_used.startswith("claude:")
                            and len(out) > 400
                            and is_delegatable(block.name)):
                        compressed = await asyncio.to_thread(
                            worker_run, block.name, out, worker_model
                        )
                        print(f"  [worker] compressed {len(out)}→{len(compressed)} chars "
                              f"via {worker_model}", file=sys.stderr)
                        out = compressed
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})
            messages.append({"role": "user", "content": results})

        print("[stopped: hit step limit]")


def cli() -> None:
    if len(sys.argv) < 2:
        print('usage: python -m ops_agent.coordinator [--claude] [--yes] [/<command>] "<task>"')
        raise SystemExit(2)
    force_claude = "--claude" in sys.argv
    auto_yes = "--yes" in sys.argv
    args = [a for a in sys.argv[1:] if a not in ("--claude", "--yes")]
    task_input = " ".join(args)

    # load commands from skills
    cfg = load_config()
    commands = load_commands(ROOT / cfg.get("skills_dir", "skills"))

    # check if input is a command
    cmd_name, extra_args = parse_command_line(task_input)
    if cmd_name:
        if cmd_name == "commands":
            print(help_text(commands))
            return
        expanded = expand_command(cmd_name, commands, extra_args)
        if expanded:
            task_input = expanded
        else:
            print(f"unknown command: /{cmd_name}")
            print(help_text(commands))
            raise SystemExit(1)

    asyncio.run(main(task_input, force_claude=force_claude, auto_yes=auto_yes))


if __name__ == "__main__":
    cli()
