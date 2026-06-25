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
    expands_to: "Provision a new Proxmox VM. Ask me: target node, hostname, VLAN, IP (or auto-assign), cores, memory (GB), disk size (GB). Follow the provision-proxmox skill procedure."
---

# Provision a Proxmox VM

## Procedure
1. **Pick a free IP and VMID.** Check the IPAM "first free" for the target VLAN *and* a live
   ping — both must agree the address is free. VMIDs follow the local convention, not the
   raw cluster nextid.
2. **Clone the golden template** to the new VMID (full clone) on a node that carries the
   target VLAN bridge. Run the clone detached so a dropped connection can't abort it.
3. **Configure** cloud-init: hostname, static IP `ip/cidr,gw`, VLAN tag on the bridge,
   cores/memory; the template already carries the standard SSH keys.
4. **Add a data disk** if the role needs one, then start the VM and wait for the agent.
5. **Apply the base build** (hardening + docker + device enrollment) via the standard role.
6. **Register** the IP in IPAM and add DNS (forward + reverse).

## Important
- Cloning and starting are additive; **destroying/overwriting an existing VMID is not** —
  confirm first.
- If the standard golden image stalls on an interactive package prompt during base config,
  it must be made non-interactive before it will complete.
