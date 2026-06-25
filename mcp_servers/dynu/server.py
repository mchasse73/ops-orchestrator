"""Dynu DNS MCP server (stdio). Public DNS records on Dynu.

Exposes tools the coordinator can call. The API key never leaves this process
(read from the env var named by DYNU_API_KEY_ENV, default DYNU_API_KEY).

    python -m mcp_servers.dynu.server
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

API = "https://api.dynu.com/v2"
mcp = FastMCP("dynu")


def _headers() -> dict:
    key_env = os.environ.get("DYNU_API_KEY_ENV", "DYNU_API_KEY")
    key = os.environ.get(key_env)
    if not key:
        raise RuntimeError(f"Dynu API key not set (env {key_env})")
    return {"API-Key": key, "accept": "application/json", "Content-Type": "application/json"}


def _domain_id(client: httpx.Client, domain: str) -> int:
    doms = client.get(f"{API}/dns", headers=_headers()).json().get("domains", [])
    for d in doms:
        if d["name"] == domain:
            return d["id"]
    raise RuntimeError(f"domain not found on this Dynu account: {domain}")


@mcp.tool()
def list_records(domain: str) -> str:
    """List DNS records for a domain (e.g. 'example.com')."""
    with httpx.Client(timeout=20) as c:
        did = _domain_id(c, domain)
        recs = c.get(f"{API}/dns/{did}/record", headers=_headers()).json().get("dnsRecords", [])
        return "\n".join(
            f"{r.get('nodeName') or '@'}.{domain} {r.get('recordType')} {r.get('ipv4Address') or r.get('textData','')} (id {r['id']})"
            for r in recs
        ) or "(no records)"


@mcp.tool()
def add_a_record(domain: str, node_name: str, ipv4: str, ttl: int = 300) -> str:
    """Create an A record. node_name is the host part (e.g. 'www'); use '' for the apex."""
    with httpx.Client(timeout=20) as c:
        did = _domain_id(c, domain)
        r = c.post(f"{API}/dns/{did}/record", headers=_headers(), json={
            "nodeName": node_name, "recordType": "A", "ipv4Address": ipv4, "state": True, "ttl": ttl,
        }).json()
        if r.get("exception"):
            return f"ERROR: {r['exception']}"
        return f"created {node_name}.{domain} A {ipv4} (id {r.get('id')})"


@mcp.tool()
def delete_record(domain: str, record_id: int) -> str:
    """Delete a record by its id (from list_records)."""
    with httpx.Client(timeout=20) as c:
        did = _domain_id(c, domain)
        resp = c.delete(f"{API}/dns/{did}/record/{record_id}", headers=_headers())
        return f"deleted record {record_id} (HTTP {resp.status_code})"


if __name__ == "__main__":
    mcp.run()
