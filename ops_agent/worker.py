"""Haiku worker — executes a single mechanical tool call cheaply.

The coordinator calls delegate(tool, args) when a step needs no judgment:
a status check, a single DNS record lookup, a VM ping. The worker spins up
a one-shot Haiku loop, runs the tool, and returns the plain-text result.

Cost rationale (Claude rates):
  Sonnet turn   ~$0.010–0.030 per turn
  Haiku turn    ~$0.002–0.005 per turn  (5–10x cheaper)

The worker only makes sense for Claude fallback turns — Ollama is free so
delegation is skipped when the coordinator is running on Ollama.
"""
from __future__ import annotations

import anthropic

# tools the coordinator is allowed to delegate — read-only, single-shot,
# no judgment required. Mutating tools must stay with the coordinator
# so the confirm gate and skill context are in play.
DELEGATABLE_PREFIXES = (
    "list_", "get_", "status", "next_free", "show_", "check_",
)


def is_delegatable(tool_name: str) -> bool:
    """True when a tool is safe to hand off to a cheap worker."""
    # strip the MCP server prefix (e.g. "proxmox__list_vms" -> "list_vms")
    bare = tool_name.split("__", 1)[-1]
    return any(bare.startswith(p) for p in DELEGATABLE_PREFIXES)


def run(tool_name: str, tool_result: str, model: str) -> str:
    """Summarise a raw tool result using Haiku.

    The coordinator already executed the tool and has the raw output.
    The worker's job is just to distil it to the key facts the coordinator
    needs — keeping the coordinator's context window lean.
    """
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                f"Tool `{tool_name}` returned the following raw output. "
                f"Extract only the key facts needed to continue the task. "
                f"Be concise — one short paragraph or a tight bullet list:\n\n"
                f"{tool_result[:4000]}"
            ),
        }],
    )
    return next((b.text for b in resp.content if b.type == "text"), tool_result)
