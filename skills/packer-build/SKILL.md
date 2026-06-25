---
name: packer-build
description: Build a fresh Ubuntu 24.04 golden template on a Proxmox node using Packer + cloud-init.
commands:
  - name: build-template
    description: Build the Ubuntu 24.04 golden template on a Proxmox node
    expands_to: "Build the Ubuntu 24.04 Packer golden template. Ask me: which Proxmox node (prox/prox1/prox2/prox3/prox4) and confirm the target VMID."
---

# Build Ubuntu 24.04 Golden Template with Packer

## Overview

Replaces the manually-maintained golden VM templates (VMID 9000–9004) with a reproducible
Packer build. The resulting template is cloud-init enabled so `deploy_base_server.yml` can
inject hostname, IP, DNS, and credentials at deploy time with no baked-in values.

## Prerequisites

- Packer v1.11+ installed (`packer version`)
- Proxmox credentials in Vault (`secret/proxmox`)
- `~/.ssh/id_ed25519` present on the machine running Packer (Beast)
- The target node must be able to reach `releases.ubuntu.com` for the ISO download

## Procedure

1. **Fetch credentials from Vault**
   ```bash
   source /ct/ops-central/scripts/beast-vault-login.sh
   export PROXMOX_PASSWORD=$(vault kv get -field=password secret/proxmox)
   export PROXMOX_HOST=$(vault kv get -field=api_host_1 secret/proxmox)
   ```

2. **Init the Proxmox plugin** (first time only)
   ```bash
   cd /ct/ops-orchestrator/packer/ubuntu-2404
   packer init ubuntu-2404.pkr.hcl
   ```

3. **Build the template**
   ```bash
   packer build \
     -var "proxmox_url=https://${PROXMOX_HOST}:8006/api2/json" \
     -var "proxmox_password=${PROXMOX_PASSWORD}" \
     -var "proxmox_node=prox1" \
     -var "template_vmid=9001" \
     ubuntu-2404.pkr.hcl
   ```

   Replace `proxmox_node` and `template_vmid` per node:
   | Node  | VMID |
   |-------|------|
   | prox  | 9000 |
   | prox1 | 9001 |
   | prox2 | 9002 |
   | prox3 | 9003 |
   | prox4 | 9004 |

4. **Verify the template** — check in Proxmox UI that the VM shows as a template with
   cloud-init drive attached.

## What the template contains

- Ubuntu 24.04 LTS minimal server
- qemu-guest-agent (required for Proxmox IP detection)
- cloud-init drive (Proxmox injects IP/DNS/hostname at deploy time)
- SSH keys for mchasse (all 5 workstations)
- SSH hardening (no password auth, MaxAuthTries 3, JumpCloud PAM stub)
- Kernel hardening (ASLR, rp_filter, no IPv6, no redirects)
- UFW (deny incoming, allow SSH)
- Fail2ban (3 retries, 1hr ban)
- Unattended security upgrades
- Base packages (git, vim, htop, btop, python3, nfs-common, etc.)

## What is NOT baked in (set at deploy time by Ansible)

- Hostname / IP / DNS / gateway — injected via Proxmox cloud-init config
- JumpCloud agent — requires connect_key from Vault, installed by `deploy_base_server.yml`
- NFS /mnt/backup mount — configured by Ansible after boot
- Application-specific packages — applied by role-specific playbooks

## Rebuild cadence

Rebuild templates when:
- New Ubuntu 24.04 point release drops
- A base package or kernel hardening change is needed
- JumpCloud PAM config changes

Rebuilding replaces the existing VMID. Existing VMs cloned from the old template are unaffected.
