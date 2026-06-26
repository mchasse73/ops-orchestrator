# ops-orchestrator

A **cost-aware multi-agent system for homelab infrastructure ops**. A coordinating
agent reads a task in plain English, pulls in only the skills and tools it needs,
and executes against your homelab — provisioning Proxmox VMs, managing DNS, building
golden templates, and so on.

> Status: **v0.1.0** — core architecture proven, all primary workflows implemented.

## How it's cheap

| Lever | What it does |
|---|---|
| **Local Ollama first** | Every turn tries your local Ollama instance (e.g. `qwen3:32b`) before calling Claude. Infra reads cost $0. Claude is the automatic fallback when Ollama fails or times out. |
| **Skills (progressive disclosure)** | Each skill contributes only a one-line description by default. The full procedure loads on demand — you only pay for what the task actually needs. |
| **Prompt caching** | The stable prefix (system prompt + skill registry) is cached with Claude — ~90% off on repeated turns. |
| **Haiku worker delegation** | Long read-only tool results are compressed by Claude Haiku before re-entering the coordinator's context. ~87% token reduction on large list outputs. |
| **Destructive-action gate** | Mutating tools (clone, delete, add record) require explicit confirmation before running. |

## Architecture

```
  ops-agent "provision a docker host on VLAN 80"
        │
        ▼
  ModelRouter  ──► Ollama (qwen3:32b, free, local)
        │           └─ falls back to Claude on error/timeout
        ▼
  Coordinator (agentic loop)
        │  cached system prompt = skill descriptions only
        │  prior context from MemPalace (cross-session memory)
        ├── load_skill(name)   → injects full SKILL.md on demand
        ├── Haiku worker       → compresses long read-only results
        └── MCP servers (stdio, local — credentials never leave the box)
              proxmox/         → list/clone/configure/start VMs; list templates
              dynu/            → public DNS records (A, CNAME, TXT…)
              technitium/      → internal/authoritative DNS records
```

Skills hold the *procedure* (judgment + context); MCP servers hold the *actions*
(the API calls). The coordinator composes them.

## Quick start

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml   # set Ollama URL, MCP server hosts, creds
export ANTHROPIC_API_KEY=...         # Claude fallback key (or `ant auth login`)
python -m ops_agent.coordinator "list the Proxmox nodes in the cluster"
```

**Flags:**
```
--claude   force Claude for this run (bypass Ollama)
--yes      auto-approve destructive actions (for automation/scripting)
```

## ops-agent shell wrapper

A convenience wrapper at `.claude/skills/ops-agent` exposes common commands with
automatic Vault credential injection (AppRole auth, no browser required):

```bash
ops-agent list-vms
ops-agent list-nodes
ops-agent next-vmid
ops-agent provision
ops-agent build-template [node] [version]   # e.g. build-template prox1 24.04
```

Add to PATH via `~/.bashrc`:
```bash
export PATH="/path/to/ops-orchestrator/.claude/skills:$PATH"
```

## Golden templates (Packer)

Ubuntu golden templates are built with Packer and stored as cloud-init-enabled
Proxmox VM templates. ISO files are stored on shared NFS (`prox-iso`) so they
are uploaded once and reused across all cluster nodes.

| VMID | Template name        | Ubuntu version  | Build node |
|------|----------------------|-----------------|------------|
| 9000 | ubuntu-2404-golden   | 24.04 LTS Noble | prox1      |
| 9200 | ubuntu-2604-golden   | 26.04 LTS       | prox3      |
| 9500 | ubuntu-2510-golden   | 25.10           | prox2      |

Templates are single instances — any node can clone from them. Build a template:

```bash
ops-agent build-template prox1 24.04      # fully specified
ops-agent build-template                  # interactive prompts
```

Each template includes: qemu-guest-agent, cloud-init, SSH hardening, UFW,
fail2ban, kernel hardening, and base packages. JumpCloud and app-specific
config are applied by Ansible at deploy time.

## MemPalace integration

The coordinator queries a local MemPalace knowledge graph at the start of each
run to surface relevant prior decisions, VM facts, and infrastructure state.
Key outcomes are saved back at the end of each run, building up cross-session
memory over time.

Configure in `config.yaml`:
```yaml
mempalace_url: "http://localhost:8766/mcp"
mempalace_wing: "ops_central"
```

Set `mempalace_url: ""` to disable.

## MCP servers

| Server | Tools |
|---|---|
| `proxmox` | `list_nodes`, `list_vms`, `list_templates`, `get_vm_config`, `get_vm_status`, `next_free_vmid`, `clone_template`, `wait_for_task`, `set_vm_config`, `add_disk`, `start_vm`, `wait_for_agent` |
| `dynu` | `list_records`, `add_a_record`, `delete_record` |
| `technitium` | `list_zones`, `list_records`, `add_record`, `delete_record`, `resync_secondary` |

Read tools bypass the destructive-action confirm gate via MCP `readOnlyHint` annotation.

## Skills

| Skill | What it covers |
|---|---|
| `provision-proxmox` | Full VM provisioning: pick template/IP/VMID, clone, configure cloud-init, start, register DNS |
| `packer-build` | Build Ubuntu golden templates with Packer; ISO on shared NFS; per-version procedure |
| `dynu-dns` | When to use Dynu vs Technitium; public exposure; safety notes |
| `technitium-dns` | Internal authoritative DNS; split-view; secondary resync |

## Layout

```
ops_agent/
  coordinator.py   CLI + agentic loop + MemPalace integration
  router.py        ModelRouter: Ollama-first, Claude fallback
  skills.py        skill registry + on-demand loader
  worker.py        Haiku sub-agent for compressing read-only results
  mempalace.py     MemPalace HTTP client
  commands.py      CLI slash commands from SKILL.md frontmatter
mcp_servers/
  proxmox/server.py
  dynu/server.py
  technitium/server.py
skills/
  provision-proxmox/SKILL.md
  packer-build/SKILL.md
  dynu-dns/SKILL.md
  technitium-dns/SKILL.md
packer/
  ubuntu.pkr.hcl            unified build for any Ubuntu version
  ubuntu-2404/http/         autoinstall config (works for all versions)
  scripts/base-config.sh    hardening provisioner
tests/
  test_commands.py
  test_mempalace.py
  test_worker.py
config.example.yaml
```

## Completed

- [x] Architecture + cost-lever wiring
- [x] Ollama-first model router with automatic Claude fallback
- [x] Dynu + Technitium + Proxmox MCP servers
- [x] Destructive-action confirm gate (`--yes` for automation)
- [x] Haiku worker delegation for mechanical steps
- [x] `defer_tools` auto-enable threshold (scale lever)
- [x] Tests (28 passing) + ruff lint + GitHub Actions CI
- [x] CLI slash commands from SKILL.md frontmatter (`/commands`)
- [x] Packer golden template builds (24.04 / 25.10 / 26.04)
- [x] MemPalace integration (cross-session persistent context)
- [x] `ops-agent` shell wrapper with Vault AppRole credential injection
