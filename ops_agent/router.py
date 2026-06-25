"""ModelRouter — try Ollama first, fall back to Claude.

Ollama is free and local; Claude is the reliable fallback. The router:
  1. Sends the request to Ollama (OpenAI-compat wire format)
  2. Normalizes the Ollama response to the coordinator's internal format
  3. Falls back to Claude on: connection error, timeout, malformed tool calls,
     or when Ollama returns plain text when tool_use was expected

Internal message format (what the coordinator uses throughout):
  {"role": "user"|"assistant", "content": <str or list of blocks>}
  blocks: {"type": "text", "text": ...}
          {"type": "tool_use", "id": ..., "name": ..., "input": {...}}
          {"type": "tool_result", "tool_use_id": ..., "content": ...}

This matches the Anthropic SDK shape, so the coordinator needs no changes
when Ollama is in play — the router emits the same objects Claude does.
"""
from __future__ import annotations

import json
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

import anthropic
import httpx

# ── normalised response (coordinator-facing) ──────────────────────────────────

@dataclass
class Block:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)

    # make it duck-type compatible with the Anthropic SDK blocks
    def __getattr__(self, item):
        return None


@dataclass
class NormResponse:
    stop_reason: str          # "end_turn" | "tool_use" | "refusal"
    content: list[Block]
    model_used: str           # "ollama:<model>" | "claude:<model>"
    usage: dict = field(default_factory=dict)

    def __iter__(self):       # so `for block in resp.content` works
        return iter(self.content)


# ── tool format conversion ────────────────────────────────────────────────────

def _to_openai_tools(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool defs to OpenAI function-calling format."""
    out = []
    for t in tools:
        if t.get("type", "").startswith("tool_search"):
            continue   # server-side tool — skip for Ollama
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return out


def _to_openai_messages(messages: list[dict], system: list[dict]) -> list[dict]:
    """Convert Anthropic-format messages + system to OpenAI format."""
    out = []
    # system prompt
    sys_text = " ".join(b.get("text", "") for b in system if isinstance(b, dict))
    if sys_text:
        out.append({"role": "system", "content": sys_text})
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        # list of blocks
        text_parts, tool_calls, tool_results = [], [], []
        for b in content:
            bt = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
            if bt == "text":
                t = b.get("text") if isinstance(b, dict) else b.text
                if t:
                    text_parts.append(t)
            elif bt == "tool_use":
                bid = b.get("id") if isinstance(b, dict) else b.id
                bn = b.get("name") if isinstance(b, dict) else b.name
                binput = b.get("input") if isinstance(b, dict) else b.input
                tool_calls.append({
                    "id": bid, "type": "function",
                    "function": {"name": bn, "arguments": json.dumps(binput)},
                })
            elif bt == "tool_result":
                tid = b.get("tool_use_id") if isinstance(b, dict) else b.tool_use_id
                tc = b.get("content") if isinstance(b, dict) else b.content
                tool_results.append({"role": "tool", "tool_call_id": tid,
                                     "content": tc if isinstance(tc, str) else json.dumps(tc)})
        if tool_calls:
            out.append({"role": "assistant",
                        "content": " ".join(text_parts) or None,
                        "tool_calls": tool_calls})
        elif text_parts:
            out.append({"role": role, "content": " ".join(text_parts)})
        out.extend(tool_results)
    return out


def _from_openai_response(resp: dict, model: str) -> NormResponse:
    """Normalise an OpenAI-format response to NormResponse."""
    choice = resp["choices"][0]
    msg = choice["message"]
    finish = choice.get("finish_reason", "stop")
    blocks: list[Block] = []
    if msg.get("content"):
        blocks.append(Block(type="text", text=msg["content"]))
    if msg.get("tool_calls"):
        for tc in msg["tool_calls"]:
            fn = tc["function"]
            try:
                args = json.loads(fn["arguments"])
            except json.JSONDecodeError as e:
                raise ValueError(f"malformed tool-call JSON from Ollama: {fn['arguments'][:120]}") from e
            blocks.append(Block(
                type="tool_use",
                id=tc.get("id") or f"ollama_{uuid.uuid4().hex[:8]}",
                name=fn["name"],
                input=args,
            ))
    stop = "tool_use" if finish == "tool_calls" else "end_turn"
    usage = resp.get("usage", {})
    return NormResponse(
        stop_reason=stop, content=blocks,
        model_used=f"ollama:{model}",
        usage={"in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0)},
    )


# ── router ────────────────────────────────────────────────────────────────────

class ModelRouter:
    """Try Ollama; fall back to Claude on any failure."""

    def __init__(self, cfg: dict):
        self.ollama_url = cfg.get("ollama_url", "http://10.200.70.25:11434")
        self.ollama_model = cfg.get("ollama_model", "qwen2.5:32b")
        self.ollama_timeout = cfg.get("ollama_timeout", 120)
        self.claude_model = cfg["models"]["coordinator"]
        self._anthropic = anthropic.Anthropic()
        self.stats = {"ollama": 0, "claude": 0, "fallbacks": 0}

    # public API the coordinator calls
    def create(self, *, system: list[dict], tools: list[dict],
               messages: list[dict], max_tokens: int = 8000) -> NormResponse:
        if not self.ollama_url:   # --claude flag or empty config → skip Ollama silently
            return self._claude(system, tools, messages, max_tokens)
        try:
            return self._ollama(system, tools, messages, max_tokens)
        except Exception as exc:
            self.stats["fallbacks"] += 1
            print(f"  [router] Ollama failed ({type(exc).__name__}: {exc}) — falling back to Claude",
                  file=sys.stderr)
            return self._claude(system, tools, messages, max_tokens)

    # ── Ollama ─────────────────────────────────────────────────────────────
    def _ollama(self, system, tools, messages, max_tokens) -> NormResponse:
        oa_messages = _to_openai_messages(messages, system)
        oa_tools = _to_openai_tools(tools)
        payload: dict[str, Any] = {
            "model": self.ollama_model,
            "messages": oa_messages,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if oa_tools:
            payload["tools"] = oa_tools
        with httpx.Client(timeout=self.ollama_timeout) as c:
            r = c.post(f"{self.ollama_url}/v1/chat/completions",
                       json=payload,
                       headers={"Content-Type": "application/json"})
            r.raise_for_status()
        resp = _from_openai_response(r.json(), self.ollama_model)
        # if tools were present but Ollama returned no tool_use AND no text, something went wrong
        if oa_tools and not resp.content:
            raise ValueError("Ollama returned empty response with tools present")
        self.stats["ollama"] += 1
        return resp

    # ── Claude fallback ────────────────────────────────────────────────────
    def _claude(self, system, tools, messages, max_tokens) -> NormResponse:
        # filter out any Ollama-specific non-Anthropic tool types
        claude_tools = [t for t in tools if not t.get("type", "").startswith("tool_search")
                        or t.get("type", "").startswith("tool_search_tool")]
        resp = self._anthropic.messages.create(
            model=self.claude_model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            tools=claude_tools or anthropic.NOT_GIVEN,
            messages=messages,
        )
        blocks = []
        for b in resp.content:
            if b.type == "text":
                blocks.append(Block(type="text", text=b.text))
            elif b.type == "tool_use":
                blocks.append(Block(type="tool_use", id=b.id, name=b.name, input=b.input))
        self.stats["claude"] += 1
        u = resp.usage
        return NormResponse(
            stop_reason=resp.stop_reason,
            content=blocks,
            model_used=f"claude:{self.claude_model}",
            usage={
                "in": u.input_tokens, "out": u.output_tokens,
                "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
            },
        )

    def summary(self) -> str:
        total = self.stats["ollama"] + self.stats["claude"]
        return (f"turns: {total} (ollama={self.stats['ollama']} "
                f"claude={self.stats['claude']} fallbacks={self.stats['fallbacks']})")
