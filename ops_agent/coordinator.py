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

import anthropic
import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .skills import load_skills, registry_block

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


def _confirm(name: str, args: dict) -> bool:
    print(f"\n⚠️  MUTATING action requested: {name}\n    args: {json.dumps(args)}", file=sys.stderr)
    try:
        return input("    Proceed? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False   # non-interactive: deny by default


async def main(task: str) -> None:
    cfg = load_config()
    skills = load_skills(ROOT / cfg.get("skills_dir", "skills"))
    client = anthropic.Anthropic()
    model = cfg["models"]["coordinator"]
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
                if defer:
                    td["defer_loading"] = True   # not in context until the model searches for it
                tools.append(td)

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

        def log_usage(u) -> None:
            usage["in"] += u.input_tokens
            usage["out"] += u.output_tokens
            usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
            usage["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
            print(f"  [turn usage] in={u.input_tokens} out={u.output_tokens} "
                  f"cache_read={getattr(u,'cache_read_input_tokens',0)}", file=sys.stderr)

        def summary() -> None:
            cost = (usage["in"] * 3 + usage["cache_read"] * 0.3 + usage["cache_write"] * 3.75
                    + usage["out"] * 15) / 1_000_000
            print(f"\n[total] uncached_in={usage['in']} cache_read={usage['cache_read']} "
                  f"cache_write={usage['cache_write']} out={usage['out']} "
                  f"| ~${cost:.5f} (Sonnet rates)", file=sys.stderr)

        # 4) manual agentic loop
        for _ in range(40):
            resp = client.messages.create(
                model=model,
                max_tokens=8000,
                thinking={"type": "adaptive"},
                system=system,
                tools=tools,
                messages=messages,
            )
            log_usage(resp.usage)
            if resp.stop_reason in ("end_turn", "refusal"):
                print("\n".join(b.text for b in resp.content if b.type == "text"))
                if resp.stop_reason == "refusal":
                    print("[refused]", getattr(resp, "stop_details", None))
                summary()
                return
            if resp.stop_reason == "pause_turn":   # server tool (tool search) still working
                messages.append({"role": "assistant", "content": resp.content})
                continue

            messages.append({"role": "assistant", "content": resp.content})
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
                        if not await asyncio.to_thread(_confirm, block.name, block.input):
                            results.append({"type": "tool_result", "tool_use_id": block.id,
                                            "content": "Operator DECLINED this action. Do not retry it; "
                                                       "pick a different approach or ask what to do."})
                            continue
                    r = await sessions[server].call_tool(real, block.input)
                    out = "\n".join(getattr(c, "text", str(c)) for c in r.content)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})
            messages.append({"role": "user", "content": results})

        print("[stopped: hit step limit]")


def cli() -> None:
    if len(sys.argv) < 2:
        print('usage: python -m ops_agent.coordinator "<task>"')
        raise SystemExit(2)
    asyncio.run(main(" ".join(sys.argv[1:])))


if __name__ == "__main__":
    cli()
