"""MemPalace client — persistent knowledge graph for cross-session context.

Connects to the MemPalace MCP server over HTTP (streamable_http transport).
Used by the coordinator to:
  - Query prior decisions and infrastructure facts at session start
  - Save key facts discovered or decided during a run

Wing convention: ops_central
Room convention: topic slug (e.g. "proxmox", "dns", "vms", "decisions")
"""
from __future__ import annotations

import sys
from typing import Any

import httpx


class MemPalaceClient:
    """Thin HTTP client for MemPalace JSON-RPC calls."""

    def __init__(self, url: str, wing: str = "ops_central"):
        self.url = url
        self.wing = wing
        self._id = 0

    def _call(self, tool: str, arguments: dict) -> Any:
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }
        try:
            r = httpx.post(self.url, json=payload, timeout=10)
            r.raise_for_status()
            result = r.json()
            if "error" in result:
                return None
            content = result.get("result", {}).get("content", [])
            if content and content[0].get("type") == "text":
                return content[0]["text"]
            return None
        except Exception as exc:
            print(f"  [mempalace] {tool} failed: {exc}", file=sys.stderr)
            return None

    def search(self, query: str, limit: int = 5) -> str | None:
        """Full-text search across all drawers."""
        return self._call("mempalace_search", {"query": query, "limit": limit})

    def query_kg(self, entity: str) -> str | None:
        """Query knowledge graph facts for an entity."""
        return self._call("mempalace_kg_query", {"entity": entity})

    def add_drawer(self, room: str, key: str, body: str) -> str | None:
        """Store a fact in a drawer. Overwrites if key exists in room."""
        return self._call("mempalace_add_drawer", {
            "wing": self.wing,
            "room": room,
            "key": key,
            "body": body,
        })

    def get_drawer(self, room: str, key: str) -> str | None:
        """Retrieve a specific drawer."""
        return self._call("mempalace_get_drawer", {
            "wing": self.wing,
            "room": room,
            "key": key,
        })

    def list_drawers(self, room: str) -> str | None:
        """List all drawers in a room."""
        return self._call("mempalace_list_drawers", {
            "wing": self.wing,
            "room": room,
        })

    def kg_add(self, subject: str, predicate: str, obj: str) -> str | None:
        """Add a knowledge graph fact."""
        return self._call("mempalace_kg_add", {
            "subject": subject,
            "predicate": predicate,
            "object": obj,
        })

    def context_for_task(self, task: str) -> str:
        """Search MemPalace for context relevant to the given task.

        Returns a formatted string ready to inject into the system prompt.
        Returns empty string if MemPalace is unreachable or nothing relevant found.
        """
        results = self.search(task, limit=5)
        if not results or results.strip() in ("", "[]", "{}"):
            return ""
        return f"## Prior context from MemPalace\n{results}\n"

    def save_run_facts(self, task: str, outcome: str) -> None:
        """Persist a summary of this run to MemPalace for future sessions."""
        import re
        # Derive a short key from the task (slug-like)
        key = re.sub(r"[^a-z0-9]+", "-", task.lower())[:60].strip("-")
        body = f"Task: {task}\nOutcome: {outcome}"
        self.add_drawer("run-history", key, body)
