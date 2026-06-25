# ops-orchestrator

A small, **cost-aware multi-agent system for infrastructure ops**. A coordinating
agent reads a task in plain English, pulls in **only the skills and tools it needs**,
and executes against your homelab — provisioning Proxmox VMs, managing Dynu and
Technitium DNS, and so on.

> Status: **v0 / actively building.** Architecture is settled; domains are being filled in.

## Why it's cheap

The whole design is built around *not* paying for context you aren't using:

| Lever | What it does |
|---|---|
| **Deferred tools + tool search** | Every infra tool is marked `defer_loading: true`. Their schemas are **not** in the prompt until the coordinator searches for the one it needs (`tool_search_tool_bm25`). A 50-tool surface costs ~0 tokens at rest. |
| **Skills (progressive disclosure)** | Each skill (`skills/<name>/SKILL.md`) contributes only a one-line description by default. The full "how to provision a Proxmox VM" body is loaded on demand via the `load_skill` tool. |
| **Prompt caching** | The stable prefix (system prompt + skill registry) is cached — ~90% off on repeated turns. |
| **Model tiering** | Coordinator runs on **Sonnet 4.6** for planning; mechanical sub-steps (an IP scan, a single DNS record) run on **Haiku 4.5**. |

## Architecture

```
  ops-agent "provision a docker host on VLAN 80"
        │
        ▼
  coordinator (Sonnet 4.6, agentic loop)
        │  small cached system prompt = skill + tool *descriptions* only
        ├── load_skill(name)         → injects skills/<name>/SKILL.md on demand
        ├── tool_search(...)         → surfaces only the matching deferred tools
        └── MCP servers (stdio, local — creds never leave the box)
              proxmox/     → clone/configure/start VMs
              dynu/        → public DNS records
              technitium/  → internal DNS records
```

Skills hold the *procedure* (the judgment); MCP servers hold the *actions* (the API
calls). The coordinator composes them.

## Quick start

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml      # set models, MCP servers, creds source
export ANTHROPIC_API_KEY=...            # or use `ant auth login`
python -m ops_agent.coordinator "add an A record dns.lab.example.com -> 10.0.0.5"
```

## Layout

```
ops_agent/coordinator.py   # the CLI + agentic loop (the 4 cost levers live here)
ops_agent/skills.py        # skill registry + on-demand loader
skills/<name>/SKILL.md      # one folder per skill (frontmatter: name, description)
mcp_servers/<name>/server.py# one stdio MCP server per domain
config.example.yaml         # models, skill dir, MCP servers, credential source
```

## Roadmap
- [x] Architecture + cost-lever wiring
- [ ] dynu MCP server (in progress) + skill
- [ ] technitium + proxmox MCP servers + skills
- [ ] Haiku sub-agent delegation for mechanical steps
- [ ] reuse ops-central `lib/infra_client.py` (Vault/Proxmox) when present
- [ ] dry-run / confirm gate for destructive actions
```
