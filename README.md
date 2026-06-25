# ops-orchestrator

A **cost-aware multi-agent system for homelab infrastructure ops**. A coordinating
agent reads a task in plain English, pulls in only the skills and tools it needs,
and executes against your homelab — provisioning Proxmox VMs, managing DNS, and so on.

> Status: **actively building** — core architecture proven, domains being filled in.

## How it's cheap

| Lever | What it does |
|---|---|
| **Local Ollama first** | Every turn tries your local Ollama instance (e.g. `qwen3:32b`) before calling Claude. Infra reads cost $0. Claude is the automatic fallback when Ollama fails or times out. |
| **Skills (progressive disclosure)** | Each skill contributes only a one-line description by default. The full procedure loads on demand — you only pay for what the task actually needs. |
| **Prompt caching** | The stable prefix (system prompt + skill registry) is cached with Claude — ~90% off on repeated turns. |
| **Destructive-action gate** | Mutating tools (clone, delete, add record) require explicit confirmation before running, preventing accidental expensive or hard-to-reverse actions. |

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
        ├── load_skill(name)   → injects full SKILL.md on demand
        └── MCP servers (stdio, local — credentials never leave the box)
              proxmox/         → list nodes/VMs, clone, configure, start
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

## MCP servers

| Server | Tools | Notes |
|---|---|---|
| `proxmox` | `list_nodes`, `list_vms`, `get_vm_config`, `get_vm_status`, `next_free_vmid`, `clone_template`, `set_vm_config`, `add_disk`, `start_vm`, `wait_for_agent` | Read tools skip the confirm gate via `readOnlyHint` |
| `dynu` | `list_records`, `add_a_record`, `delete_record` | Public DNS on Dynu |
| `technitium` | `list_zones`, `list_records`, `add_record`, `delete_record`, `resync_secondary` | Internal/authoritative DNS; read tools skip confirm gate |

## Skills

Skills live in `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`).
Only the description sits in context by default; call `load_skill(name)` to inject the
full procedure before acting.

| Skill | What it covers |
|---|---|
| `provision-proxmox` | Full VM provisioning workflow: pick IP/VMID, clone template, configure, start, run base build |
| `dynu-dns` | When to use Dynu vs Technitium, how public exposure works, safety notes |
| `technitium-dns` | Internal authoritative DNS, split-view DNS, secondary resync |

## Configuration

```yaml
# config.yaml (gitignored — copy from config.example.yaml)
ollama_url: "http://ollama.example.lan:11434"
ollama_model: "qwen3:32b"      # or qwen2.5:32b, qwen2.5:14b, llama3.1:8b…
ollama_timeout: 120

models:
  coordinator: claude-sonnet-4-6   # Claude fallback
  worker: claude-haiku-4-5

mcp_servers:
  - name: proxmox
    command: ["python", "-m", "mcp_servers.proxmox.server"]
    env: {PROXMOX_HOST: "proxmox.example.lan", PROXMOX_PASSWORD_ENV: PROXMOX_PASSWORD}
  - name: dynu
    command: ["python", "-m", "mcp_servers.dynu.server"]
    env: {DYNU_API_KEY_ENV: DYNU_API_KEY}
  - name: technitium
    command: ["python", "-m", "mcp_servers.technitium.server"]
    env: {TECHNITIUM_URL: "https://technitium.example.lan", TECHNITIUM_TOKEN_ENV: TECHNITIUM_TOKEN}

confirm_destructive: true   # set false (or use --yes) to skip interactive gate
```

## Layout

```
ops_agent/
  coordinator.py   CLI + agentic loop
  router.py        ModelRouter: Ollama-first, Claude fallback
  skills.py        skill registry + on-demand loader
mcp_servers/
  proxmox/server.py
  dynu/server.py
  technitium/server.py
skills/
  provision-proxmox/SKILL.md
  dynu-dns/SKILL.md
  technitium-dns/SKILL.md
config.example.yaml
```

## Roadmap

- [x] Architecture + cost-lever wiring
- [x] Dynu MCP server (public DNS)
- [x] Technitium MCP server (internal DNS) — read + write tools
- [x] Proxmox MCP server — 10 tools, read/mutate split
- [x] Ollama-first model router with automatic Claude fallback
- [x] Destructive-action confirm gate (`--yes` for automation)
- [ ] Haiku sub-agent delegation for mechanical steps (#3)
- [ ] `defer_tools` auto-enable threshold (#5)
- [ ] Tests + lint CI (#6)
