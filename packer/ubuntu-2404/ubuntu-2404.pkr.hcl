packer {
  required_plugins {
    proxmox = {
      version = ">= 1.1.8"
      source  = "github.com/hashicorp/proxmox"
    }
  }
}

# ── Variables ──────────────────────────────────────────────────────────────────

variable "proxmox_url" {
  description = "Proxmox API URL (e.g. https://10.200.99.7:8006/api2/json)"
  type        = string
}

variable "proxmox_username" {
  description = "Proxmox username (e.g. root@pam)"
  type        = string
  default     = "root@pam"
}

variable "proxmox_password" {
  description = "Proxmox password"
  type        = string
  sensitive   = true
}

variable "proxmox_node" {
  description = "Target Proxmox node name"
  type        = string
  default     = "prox1"
}

variable "template_vmid" {
  description = "VMID for the resulting template (9001 on prox1, etc)"
  type        = number
  default     = 9001
}

variable "template_name" {
  description = "Template name in Proxmox"
  type        = string
  default     = "ubuntu-2404-golden"
}

variable "ubuntu_iso_url" {
  description = "URL to Ubuntu 24.04 server ISO"
  type        = string
  default     = "https://releases.ubuntu.com/24.04/ubuntu-24.04.2-live-server-amd64.iso"
}

variable "ubuntu_iso_checksum" {
  description = "SHA256 of the ISO"
  type        = string
  default     = "sha256:d6dab0c3a657a0f6e86c62addc8cc2e155e28b7b7a7c0e40e85e0cd65df20e56"
}

# ── Build ──────────────────────────────────────────────────────────────────────

source "proxmox-iso" "ubuntu-2404" {
  proxmox_url              = var.proxmox_url
  username                 = var.proxmox_username
  password                 = var.proxmox_password
  insecure_skip_tls_verify = true
  node                     = var.proxmox_node

  vm_id   = var.template_vmid
  vm_name = var.template_name
  tags    = "template;ubuntu;golden"

  # ISO
  boot_iso {
    iso_url          = var.ubuntu_iso_url
    iso_checksum     = var.ubuntu_iso_checksum
    iso_storage_pool = "local"
    unmount          = true
  }

  # Hardware
  cpu_type = "host"
  cores    = 2
  memory   = 2048

  # Boot disk — cloud-init enabled scsi
  disks {
    disk_size    = "20G"
    storage_pool = "local-lvm"
    type         = "scsi"
  }

  # Cloud-init drive (required for cloud-init to work at deploy time)
  cloud_init              = true
  cloud_init_storage_pool = "local-lvm"

  # Network
  network_adapters {
    model  = "virtio"
    bridge = "vmbr0"
  }

  # qemu-guest-agent (required for Proxmox IP detection + graceful shutdown)
  qemu_agent = true

  # Boot command — triggers Ubuntu autoinstall via cloud-init subiquity
  boot_wait = "5s"
  boot_command = [
    "c<wait>",
    "linux /casper/vmlinuz --- autoinstall ds=nocloud-net\\;s=http://{{ .HTTPIP }}:{{ .HTTPPort }}/ <enter><wait>",
    "initrd /casper/initrd <enter><wait>",
    "boot <enter>"
  ]

  # HTTP server that serves the autoinstall config
  http_directory = "http"
  http_port_min  = 8802
  http_port_max  = 8810

  # SSH connection (used by Packer after install to run provisioners)
  communicator           = "ssh"
  ssh_username           = "mchasse"
  ssh_private_key_file   = "~/.ssh/id_ed25519"
  ssh_timeout            = "30m"
  ssh_handshake_attempts = 300

  # Convert to template when done
  template_description = "Ubuntu 24.04 LTS golden template — built by Packer"
}

build {
  name    = "ubuntu-2404-golden"
  sources = ["source.proxmox-iso.ubuntu-2404"]

  # Hardening and base configuration script
  provisioner "shell" {
    script = "scripts/base-config.sh"
  }

  # cloud-init cleanup so Proxmox can inject per-VM config at deploy time
  provisioner "shell" {
    inline = [
      "sudo cloud-init clean --logs --seed",
      "sudo truncate -s 0 /etc/machine-id",
      "sudo rm -f /var/lib/dbus/machine-id",
      "sudo ln -s /etc/machine-id /var/lib/dbus/machine-id",
      "sudo sync"
    ]
  }
}
