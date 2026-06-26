---
name: provision-proxmox
description: Provision a Proxmox VM from a golden template (clone, set IP/VLAN/resources, start, base config).
commands:
  - name: list-vms
    description: Show all VMs in the cluster
    expands_to: "List all VMs across the cluster with their status and node assignment."
  - name: list-nodes
    description: Show all Proxmox nodes
    expands_to: "List all Proxmox cluster nodes with their status and resource usage."
  - name: next-vmid
    description: Get the next available VMID
    expands_to: "What is the next available VMID in the cluster?"
  - name: provision
    description: Provision a new VM (guided)
    expands_to: "Provision a new Proxmox VM. Ask me: Ubuntu version, target node, hostname, VLAN, IP (or auto-assign), cores, memory (GB), disk size (GB). Follow the provision-proxmox skill procedure."
---

# Provision a Proxmox VM

## Golden Templates

Always call `list_templates` first to confirm the template exists and which node it's on.

| VMID | Name                 | Ubuntu Version  | Node  |
|------|----------------------|-----------------|-------|
| 9000 | ubuntu-2404-golden   | 24.04 LTS Noble | prox1 |
| 9200 | ubuntu-2604-golden   | 26.04 LTS       | prox3 |
| 9500 | ubuntu-2510-golden   | 25.10           | prox2 |

**Default: use 24.04 LTS (VMID 9000) unless the user requests a specific version.**

Templates are built by Packer and are cloud-init enabled. Proxmox injects hostname,
IP, DNS, and gateway at deploy time — nothing is baked into the template.

## VLAN / Network Map

| VLAN name  | Tag | Subnet         | Gateway      | DNS                    |
|------------|-----|----------------|--------------|------------------------|
| xeronine   | —   | 10.200.99.0/24 | 10.200.99.1  | 10.200.99.2, 10.200.99.3 |
| hosting    | 70  | 10.200.70.0/24 | 10.200.70.1  | 10.200.99.2, 10.200.99.3 |
| servers    | 80  | 10.200.80.0/24 | 10.200.80.1  | 10.200.99.2, 10.200.99.3 |

All nodes use bridge `vmbr0`. VLAN tag is set on the NIC (`net0`).

## Procedure

1. **Ask the user for:**
   - Ubuntu version (default: 24.04)
   - Target node (prox / prox1 / prox2 / prox3 / prox4)
   - Hostname
   - VLAN (xeronine / hosting / servers)
   - IP address (or "auto" to ping-scan and find a free one)
   - Cores (default: 2), Memory in GB (default: 2), Disk size (default: 20G)

2. **Validate the IP is free.** Ping it — if it responds, pick a different one.
   Use `next_free_vmid` for the VMID.

3. **Find the template.** Call `list_templates` and confirm the template VMID and node.
   Clone can target a different node than the template — Proxmox handles the migration.

4. **Clone the template** via `clone_template`.
   - `template_vmid`: from step 3
   - `node`: the node where the template lives (from `list_templates`)
   - `new_vmid`: from step 2
   - `name`: the hostname
   - The clone UPID is returned — pass it to `wait_for_task` before configuring.

5. **Wait for clone** via `wait_for_task(node, upid, timeout_s=180)`.

6. **Configure cloud-init** via `set_vm_config`:
   - `ipconfig0`: `ip=<IP>/<prefix>,gw=<gateway>` (e.g. `ip=10.200.80.25/24,gw=10.200.80.1`)
   - `nameserver`: `10.200.99.2 10.200.99.3`
   - `searchdomain`: `xeronine.local`
   - `cores`, `memory` (in MB)
   - If VLAN ≠ xeronine, also set `net0`: `virtio,bridge=vmbr0,tag=<vlan_tag>`

7. **Start the VM** via `start_vm`, then `wait_for_agent` (timeout 300s for first boot).

8. **Register DNS** via the technitium-dns skill:
   - Add A record: `<hostname>.xeronine.local → <IP>`

## Important

- Cloning and starting are **additive** — never overwrite an existing VMID without confirming.
- The clone runs async — always `wait_for_task` before calling `set_vm_config`.
- JumpCloud agent is **not** in the template — it is installed separately by Ansible after boot
  (requires connect_key from Vault). The template includes the PAM stub; it's a no-op until
  the agent is installed.
- cloud-init runs on first boot and may take 2–3 min. `wait_for_agent` confirms it's done.
