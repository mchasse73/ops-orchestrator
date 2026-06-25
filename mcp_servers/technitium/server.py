"""Technitium DNS MCP server (stdio). Internal/authoritative DNS.

Env: TECHNITIUM_URL (e.g. https://technitium.example.lan), token in the env var named by
TECHNITIUM_TOKEN_ENV (default TECHNITIUM_TOKEN). Self-signed cert -> verify off.

    python -m mcp_servers.technitium.server
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("technitium")


def _cfg() -> tuple[str, str]:
    url = os.environ["TECHNITIUM_URL"].rstrip("/")
    token = os.environ.get(os.environ.get("TECHNITIUM_TOKEN_ENV", "TECHNITIUM_TOKEN"))
    if not token:
        raise RuntimeError("Technitium token not set")
    return url, token


@mcp.tool()
def add_record(zone: str, domain: str, type: str, value: str, ttl: int = 300) -> str:
    """Add a record to a primary zone. type is A/AAAA/CNAME/PTR/TXT; value is the address/target."""
    url, token = _cfg()
    params = {"token": token, "zone": zone, "domain": domain, "type": type, "ttl": ttl}
    # the value param name depends on record type
    params["ipAddress" if type in ("A", "AAAA") else
           "cname" if type == "CNAME" else
           "ptrName" if type == "PTR" else "text"] = value
    with httpx.Client(verify=False, timeout=15) as c:
        r = c.get(f"{url}/api/zones/records/add", params=params).json()
        return f"add {domain} {type} {value}: {r.get('status')} {r.get('errorMessage','')}"


@mcp.tool()
def delete_record(zone: str, domain: str, type: str, value: str) -> str:
    """Delete a record (destructive — confirm first)."""
    url, token = _cfg()
    params = {"token": token, "zone": zone, "domain": domain, "type": type}
    params["ipAddress" if type in ("A", "AAAA") else "value"] = value
    with httpx.Client(verify=False, timeout=15) as c:
        r = c.get(f"{url}/api/zones/records/delete", params=params).json()
        return f"delete {domain} {type}: {r.get('status')}"


@mcp.tool()
def resync_secondary(secondary_url: str, secondary_token: str, zone: str) -> str:
    """Force a secondary (NS2) to re-pull a zone from the primary."""
    with httpx.Client(verify=False, timeout=15) as c:
        r = c.get(f"{secondary_url.rstrip('/')}/api/zones/resync",
                  params={"token": secondary_token, "zone": zone}).json()
        return f"resync {zone}: {r.get('status')}"


if __name__ == "__main__":
    mcp.run()
