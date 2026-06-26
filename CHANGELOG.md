# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com) conventions.

## [Unreleased]

### Added
- FastAPI HTTP server (`ops_agent/server.py`) — wraps coordinator as a network service
- SSE streaming for `/run` endpoint — output streams line by line as model generates
- `/setup.sh` endpoint — one-command bootstrap for any Linux machine on the network
- `bin/ops-remote` CLI client — pure stdlib Python, no pip dependencies required
- `deploy/install.sh` — full deployment script for the ops server
- `deploy/ops-orchestrator.service` — systemd unit for auto-start and restart
- `ops.xeronine.local` VM provisioned (VMID 101, 10.200.99.20, Ubuntu 24.04, 4c/8GB/40GB)
- Ubuntu cloud image template builds via SSH+qm (replaces Packer ISO approach)
  - VMID 9000: ubuntu-2404-golden (Noble), VMID 9200: ubuntu-2604-golden (Resolute),
    VMID 9500: ubuntu-2510-golden (Questing) — all on prox2 via cloud-images.ubuntu.com
- DNS record: `ops.xeronine.local → 10.200.99.20`, `ai.xeronine.local → 10.200.70.25`

### Changed
- `build-template` command switched from Packer ISO install to Ubuntu cloud image import
  — 5 min build vs 30+ min ISO install; no boot command injection, no SSH timeout issues
- System prompt tightened to prevent model hallucinating extra actions beyond stated task
- MemPalace search limit reduced to 3 results (was 5) to reduce confusing context injection

### Fixed
- SSE streaming: `stdin=DEVNULL` prevents confirm gate from hanging the stream
- SSE streaming: merged stdout+stderr into single pipe — eliminates dual-pipe deadlock
- `PYTHONUNBUFFERED=1` env on coordinator subprocess — immediate stdout flush
- `health` endpoint reads `ollama_url` from config.yaml not env var

## [1.0.0] - 2026-06-26

### Added
- MemPalace integration (`ops_agent/mempalace.py`) — queries prior context at run start,
  persists key facts at run end; connects via HTTP MCP to Beast at `localhost:8766`
- `list_templates` Proxmox tool — lists all VM templates with VMID, name, node
- `wait_for_task` Proxmox tool — polls a Proxmox task UPID until completion
- Packer builds for Ubuntu 25.10 (VMID 9500) and 26.04 LTS (VMID 9200)
- 11 unit tests for MemPalaceClient (28 total passing)

### Changed
- `provision-proxmox` skill updated with new single-template VMID scheme,
  full VLAN/network map, and step-by-step procedure using `list_templates` + `wait_for_task`
- `ops-agent build-template` now uses a single template per Ubuntu version
  (cloneable to any node) instead of per-node templates
- ISO storage changed to shared `prox-iso` NFS — ISO uploaded once, reused by all nodes
- VMID scheme: 9000=24.04 LTS, 9200=26.04 LTS, 9500=25.10

### Fixed
- `build-template` VMID 9100 conflict with `slayerrealms-amp` (moved 25.10 to 9500)
- `ops-agent` confirm prompt no longer blocks non-interactive builds (`YES=1` env var)
- MemPalace empty URL correctly short-circuits without making HTTP calls

## [0.1.0] - 2026-06-25

### Added
- Core agentic coordinator with Ollama-first routing + Claude fallback
- Proxmox MCP server — list nodes/VMs, next VMID, clone/configure/start VM
- Technitium DNS MCP server — list zones, list/add/delete records
- Dynu DNS MCP server — list/add/delete records
- Progressive skill disclosure — skills load on-demand via `load_skill` tool
- Destructive-action confirm gate — mutating tools prompt y/N (or `--yes` to bypass)
- Haiku worker compression — ~87% token reduction on large read-only results
- `defer_tools` scale lever with auto-enable threshold
- Prompt caching on stable system prefix
- CLI slash commands (`/list-vms`, `/list-nodes`, `/next-vmid`, `/provision`, `/commands`)
- `ops-agent` shell wrapper with Vault AppRole auth and Proxmox credential injection
- Packer-based Ubuntu golden template builds for 24.04 LTS
- `packer-build` skill with build procedure
- GitHub Actions CI — ruff lint + pytest on Python 3.9–3.11
- 17 unit tests
