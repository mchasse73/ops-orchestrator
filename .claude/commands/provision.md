---
name: provision
description: Provision a new Proxmox VM with guided setup
---

cd /ct/ops-orchestrator && python -m ops_agent.coordinator "Provision a new Proxmox VM. Ask me: target node, hostname, VLAN, IP (or auto-assign), cores, memory (GB), disk size (GB). Follow the provision-proxmox skill procedure."
