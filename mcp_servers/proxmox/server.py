"""Proxmox MCP server (stdio) — STUB.

v0 placeholder so the coordinator can launch all configured servers. The real tools
(clone_template, set_config, start_vm, ...) will wrap the Proxmox API — or, when running
inside ops-central, reuse lib/infra_client.py:ProxmoxClient directly.

    python -m mcp_servers.proxmox.server
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("proxmox")


@mcp.tool()
def status() -> str:
    """Report that the Proxmox server is a stub (no actions implemented yet)."""
    return ("proxmox MCP server is a stub. Planned tools: list_nodes, next_free_vmid, "
            "clone_template, set_vm_config, add_disk, start_vm, run_base_build. "
            "Follow the provision-proxmox skill for the procedure.")


if __name__ == "__main__":
    mcp.run()
