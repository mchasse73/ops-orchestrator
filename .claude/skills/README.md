# ops-orchestrator Skills

## ops

CLI wrapper for ops-orchestrator commands.

**Usage:**
```bash
! ops list-vms      # List all VMs in the cluster
! ops list-nodes    # Show all Proxmox nodes
! ops next-vmid     # Get the next available VMID
! ops provision     # Provision a new VM (guided)
```

All commands delegate to the ops-orchestrator Python agent with appropriate task expansion.
