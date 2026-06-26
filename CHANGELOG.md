# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com) conventions.

## [Unreleased]

## [0.1.0] - 2026-06-25

### Added
- Core agentic coordinator (`ops_agent/coordinator.py`) with Ollama-first routing + Claude fallback
- Proxmox MCP server — list nodes/VMs, next VMID, clone/configure/start VM (10 tools)
- Technitium DNS MCP server — list zones, list/add/delete records
- Dynu DNS MCP server — list/add/delete records
- Progressive skill disclosure — skills load on-demand via `load_skill` tool
- Destructive-action confirm gate — mutating tools prompt y/N (or `--yes` to bypass)
- Haiku worker compression — long read-only tool results summarised before re-entering context
- `defer_tools` scale lever with auto-enable threshold (`auto_defer_tool_count`)
- Prompt caching on stable system prefix
- CLI slash commands (`/list-vms`, `/list-nodes`, `/next-vmid`, `/provision`, `/commands`)
- `ops-agent` shell wrapper with Vault AppRole auth and Proxmox credential injection
- Packer-based Ubuntu golden template builds (`packer/ubuntu.pkr.hcl`)
  - Ubuntu 24.04 LTS (VMID 9000), 25.10 (VMID 9100), 26.04 LTS (VMID 9200)
  - Shared ISO storage on `prox-iso` NFS (one upload, all nodes)
  - Interactive prompts for node and version selection
  - SSH hardening, UFW, fail2ban, kernel hardening, unattended upgrades
  - cloud-init cleaned so Proxmox injects IP/DNS/hostname at deploy time
- `skills/packer-build/SKILL.md` — procedure for Packer template builds
- GitHub Actions CI — ruff lint + pytest on Python 3.9–3.11
- 17 unit tests (`tests/test_commands.py`, `tests/test_worker.py`)
- `ruff.toml` — E, W, F, I, B rules; isort config
