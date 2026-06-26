# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com) conventions.

## [Unreleased]

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
