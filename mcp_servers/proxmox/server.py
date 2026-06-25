"""Proxmox VE MCP server (stdio).

Env (set in config.yaml, never hardcoded):
  PROXMOX_HOST          hostname/IP of any cluster node (default proxmox.example.lan)
  PROXMOX_PORT          API port (default 8006)
  PROXMOX_USER          username@realm (default root@pam)
  PROXMOX_PASSWORD_ENV  name of the env var holding the password (default PROXMOX_PASSWORD)

    python -m mcp_servers.proxmox.server
"""
from __future__ import annotations

import os
import time

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("proxmox")


# ── auth ──────────────────────────────────────────────────────────────────────

def _client() -> tuple[str, dict]:
    """Return (base_url, auth_headers) after ticket auth."""
    host = os.environ.get("PROXMOX_HOST", "proxmox.example.lan")
    port = os.environ.get("PROXMOX_PORT", "8006")
    user = os.environ.get("PROXMOX_USER", "root@pam")
    pw_env = os.environ.get("PROXMOX_PASSWORD_ENV", "PROXMOX_PASSWORD")
    password = os.environ.get(pw_env, "")
    if not password:
        raise RuntimeError(f"Proxmox password not set (env var: {pw_env})")
    base = f"https://{host}:{port}"
    with httpx.Client(verify=False, timeout=15) as c:
        r = c.post(f"{base}/api2/json/access/ticket",
                   data={"username": user, "password": password})
        r.raise_for_status()
        data = r.json()["data"]
    return base, {
        "Cookie": f"PVEAuthCookie={data['ticket']}",
        "CSRFPreventionToken": data["CSRFPreventionToken"],
    }


def _get(path: str, params: dict | None = None) -> object:
    base, h = _client()
    with httpx.Client(verify=False, timeout=20) as c:
        r = c.get(f"{base}{path}", headers=h, params=params or {})
        r.raise_for_status()
        return r.json().get("data", {})


def _post(path: str, data: dict | None = None) -> object:
    base, h = _client()
    with httpx.Client(verify=False, timeout=30) as c:
        r = c.post(f"{base}{path}", headers=h, data=data or {})
        r.raise_for_status()
        return r.json().get("data", {})


def _put(path: str, data: dict | None = None) -> object:
    base, h = _client()
    with httpx.Client(verify=False, timeout=20) as c:
        r = c.put(f"{base}{path}", headers=h, data=data or {})
        r.raise_for_status()
        return r.json().get("data", {})


# ── read-only tools ───────────────────────────────────────────────────────────

@mcp.tool(annotations={"readOnlyHint": True})
def list_nodes() -> str:
    """List all Proxmox cluster nodes with status and resource usage."""
    nodes = _get("/api2/json/nodes")
    lines = []
    for n in sorted(nodes, key=lambda x: x.get("node", "")):
        cpu = round(n.get("cpu", 0) * 100, 1)
        mem_gb = round(n.get("mem", 0) / 1024 ** 3, 1)
        maxmem_gb = round(n.get("maxmem", 0) / 1024 ** 3, 1)
        lines.append(
            f"{n['node']:12}  status={n.get('status', '?'):7}  "
            f"cpu={cpu}%  mem={mem_gb}/{maxmem_gb}GB"
        )
    return "\n".join(lines) or "(no nodes)"


@mcp.tool(annotations={"readOnlyHint": True})
def list_vms(node: str = "") -> str:
    """List VMs across the cluster or on a specific node. Shows VMID, name, status, node."""
    resources = _get("/api2/json/cluster/resources", {"type": "vm"})
    if node:
        resources = [r for r in resources if r.get("node") == node]
    lines = []
    for r in sorted(resources, key=lambda x: x.get("vmid", 0)):
        lines.append(
            f"vmid={r.get('vmid', '?'):5}  {r.get('name', '(unnamed)'):28}  "
            f"status={r.get('status', '?'):8}  node={r.get('node', '?'):8}  "
            f"type={r.get('type', '?')}"
        )
    return "\n".join(lines) or "(no VMs found)"


@mcp.tool(annotations={"readOnlyHint": True})
def get_vm_config(node: str, vmid: int) -> str:
    """Get the full config for a VM (cloud-init, disks, network, memory, cores)."""
    cfg = _get(f"/api2/json/nodes/{node}/qemu/{vmid}/config")
    return "\n".join(f"{k}: {v}" for k, v in sorted(cfg.items()))


@mcp.tool(annotations={"readOnlyHint": True})
def get_vm_status(node: str, vmid: int) -> str:
    """Get runtime status of a VM (running/stopped, uptime, CPU/mem usage)."""
    s = _get(f"/api2/json/nodes/{node}/qemu/{vmid}/status/current")
    return (
        f"status={s.get('status', '?')}  uptime={s.get('uptime', 0)}s  "
        f"cpu={round(s.get('cpu', 0) * 100, 1)}%  "
        f"mem={round(s.get('mem', 0) / 1024 ** 2)}MB/"
        f"{round(s.get('maxmem', 0) / 1024 ** 2)}MB"
    )


@mcp.tool(annotations={"readOnlyHint": True})
def next_free_vmid() -> str:
    """Return the next available VMID according to the cluster."""
    vmid = _get("/api2/json/cluster/nextid")
    return f"next free VMID: {vmid}"


# ── mutating tools (trigger the confirm gate) ─────────────────────────────────

@mcp.tool()
def clone_template(node: str, template_vmid: int, new_vmid: int, name: str,
                   full: bool = True) -> str:
    """Clone a template VM to a new VMID. full=True for a self-contained clone (recommended).
    Returns a Proxmox task UPID — the clone runs async and takes 30–120s."""
    result = _post(f"/api2/json/nodes/{node}/qemu/{template_vmid}/clone", {
        "newid": new_vmid, "name": name, "full": int(full),
    })
    return f"clone task started: UPID={result}  ({template_vmid} -> {new_vmid} '{name}')"


@mcp.tool()
def set_vm_config(node: str, vmid: int, cores: int = 0, memory_mb: int = 0,
                  ipconfig0: str = "", nameserver: str = "", searchdomain: str = "",
                  ciuser: str = "", sshkeys: str = "") -> str:
    """Configure VM resources and cloud-init settings.
    ipconfig0 format: 'ip=10.0.0.5/24,gw=10.0.0.1'
    Leave a field at 0/"" to skip it."""
    data: dict = {}
    if cores:
        data["cores"] = cores
    if memory_mb:
        data["memory"] = memory_mb
    if ipconfig0:
        data["ipconfig0"] = ipconfig0
    if nameserver:
        data["nameserver"] = nameserver
    if searchdomain:
        data["searchdomain"] = searchdomain
    if ciuser:
        data["ciuser"] = ciuser
    if sshkeys:
        data["sshkeys"] = sshkeys
    if not data:
        return "nothing to set (all fields blank/zero)"
    _put(f"/api2/json/nodes/{node}/qemu/{vmid}/config", data)
    return f"config updated on {node}/{vmid}: {list(data.keys())}"


@mcp.tool()
def add_disk(node: str, vmid: int, storage: str, size_gb: int,
             device: str = "scsi1") -> str:
    """Add a data disk to a VM.
    device: scsi1, scsi2, virtio1, etc. (scsi0 is normally the OS disk)."""
    _put(f"/api2/json/nodes/{node}/qemu/{vmid}/config",
         {device: f"{storage}:{size_gb}"})
    return f"disk {device} ({size_gb}GB on {storage}) added to {node}/{vmid}"


@mcp.tool()
def start_vm(node: str, vmid: int) -> str:
    """Start a VM. Returns the Proxmox task UPID."""
    result = _post(f"/api2/json/nodes/{node}/qemu/{vmid}/status/start")
    return f"start task: UPID={result}"


@mcp.tool()
def wait_for_agent(node: str, vmid: int, timeout_s: int = 120) -> str:
    """Poll the QEMU guest agent until it responds (VM booted + agent running) or timeout.
    Use after start_vm before running Ansible — confirms cloud-init is ready."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            _post(f"/api2/json/nodes/{node}/qemu/{vmid}/agent/ping")
            return f"guest agent responded on {node}/{vmid} — VM ready"
        except Exception:
            time.sleep(5)
    return f"timeout after {timeout_s}s — VM may still be booting; check manually"


if __name__ == "__main__":
    mcp.run()
