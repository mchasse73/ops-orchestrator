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


# ── read-only tools ───────────────────────────────────────────────────────────

@mcp.tool(annotations={"readOnlyHint": True})
def list_zones() -> str:
    """List all DNS zones on this Technitium server."""
    url, token = _cfg()
    with httpx.Client(verify=False, timeout=15) as c:
        r = c.get(f"{url}/api/zones/list", params={"token": token}).json()
    zones = r.get("response", {}).get("zones", [])
    lines = []
    for z in zones:
        lines.append(
            f"{z.get('name','?'):40}  type={z.get('type','?'):10}  "
            f"disabled={z.get('disabled', False)}"
        )
    return "\n".join(lines) or "(no zones)"


@mcp.tool(annotations={"readOnlyHint": True})
def list_records(zone: str, domain: str = "") -> str:
    """List DNS records in a zone. Optionally filter to a specific domain/hostname."""
    url, token = _cfg()
    params = {"token": token, "zone": zone}
    if domain:
        params["domain"] = domain
    with httpx.Client(verify=False, timeout=15) as c:
        r = c.get(f"{url}/api/zones/records/get", params=params).json()
    records = r.get("response", {}).get("records", [])
    lines = []
    for rec in records:
        rtype = rec.get("type", "?")
        name = rec.get("name", "?")
        rdata = rec.get("rData", {})
        value = (rdata.get("ipAddress") or rdata.get("cname") or
                 rdata.get("value") or rdata.get("nameServer") or
                 str(rdata))
        lines.append(f"{name:40}  {rtype:8}  {value}")
    return "\n".join(lines) or "(no records)"


# ── mutating tools ────────────────────────────────────────────────────────────

@mcp.tool()
def add_record(zone: str, domain: str, type: str, value: str, ttl: int = 300) -> str:
    """Add a record to a primary zone. type is A/AAAA/CNAME/PTR/TXT; value is the address/target.
    domain must be the FQDN e.g. 'host.example.com' not just 'host'."""
    url, token = _cfg()
    params = {"token": token, "zone": zone, "domain": domain, "type": type, "ttl": ttl}
    params["ipAddress" if type in ("A", "AAAA") else
           "cname" if type == "CNAME" else
           "ptrName" if type == "PTR" else "text"] = value
    with httpx.Client(verify=False, timeout=15) as c:
        r = c.get(f"{url}/api/zones/records/add", params=params).json()
    return f"add {domain} {type} {value}: {r.get('status')} {r.get('errorMessage', '')}"


@mcp.tool()
def delete_record(zone: str, domain: str, type: str, value: str) -> str:
    """Delete a record (destructive — confirm first).
    domain must be the FQDN e.g. 'host.example.com' not just 'host'."""
    url, token = _cfg()
    params = {"token": token, "zone": zone, "domain": domain, "type": type}
    params["ipAddress" if type in ("A", "AAAA") else "value"] = value
    with httpx.Client(verify=False, timeout=15) as c:
        r = c.get(f"{url}/api/zones/records/delete", params=params).json()
    return f"delete {domain} {type}: {r.get('status')}"


@mcp.tool()
def resync_secondary(secondary_url: str, secondary_token: str, zone: str) -> str:
    """Force a secondary (NS2) to re-pull a zone from the primary after adding records."""
    with httpx.Client(verify=False, timeout=15) as c:
        r = c.get(f"{secondary_url.rstrip('/')}/api/zones/resync",
                  params={"token": secondary_token, "zone": zone}).json()
    return f"resync {zone}: {r.get('status')}"


if __name__ == "__main__":
    mcp.run()
