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
  type    = string
  default = "root@pam"
}

variable "proxmox_password" {
  type      = string
  sensitive = true
}

variable "proxmox_node" {
  description = "Target Proxmox node name"
  type        = string
  default     = "prox1"
}

variable "template_vmid" {
  description = "VMID for the resulting template"
  type        = number
}

variable "template_name" {
  description = "Template name in Proxmox"
  type        = string
}

variable "iso_url" {
  description = "Full URL to the Ubuntu server ISO"
  type        = string
}

variable "iso_checksum" {
  description = "sha256:<hex> checksum of the ISO"
  type        = string
}

variable "iso_storage_pool" {
  description = "Proxmox storage pool for the ISO (shared = prox-iso)"
  type        = string
  default     = "prox-iso"
}

variable "autoinstall_dir" {
  description = "Path to directory containing user-data and meta-data for this Ubuntu version"
  type        = string
}

# ── Build ──────────────────────────────────────────────────────────────────────

source "proxmox-iso" "ubuntu" {
  proxmox_url              = var.proxmox_url
  username                 = var.proxmox_username
  password                 = var.proxmox_password
  insecure_skip_tls_verify = true
  node                     = var.proxmox_node
  task_timeout             = "15m"

  vm_id   = var.template_vmid
  vm_name = var.template_name
  tags    = "template;ubuntu;golden"

  # ISO — stored on shared prox-iso NFS so all nodes can reuse it
  boot_iso {
    iso_url          = var.iso_url
    iso_checksum     = var.iso_checksum
    iso_storage_pool = var.iso_storage_pool
    unmount          = true
  }

  # Hardware
  cpu_type = "host"
  cores    = 2
  memory   = 2048

  # Boot disk — scsi with cloud-init
  disks {
    disk_size    = "20G"
    storage_pool = "local-lvm"
    type         = "scsi"
  }

  # Cloud-init drive (Proxmox injects IP/DNS/hostname at deploy time)
  cloud_init              = true
  cloud_init_storage_pool = "local-lvm"

  # Network
  network_adapters {
    model  = "virtio"
    bridge = "vmbr0"
  }

  qemu_agent = true

  # Boot command — Ubuntu subiquity autoinstall via nocloud HTTP
  boot_wait = "5s"
  boot_command = [
    "c<wait>",
    "linux /casper/vmlinuz --- autoinstall ds=nocloud-net\\;s=http://{{ .HTTPIP }}:{{ .HTTPPort }}/ <enter><wait>",
    "initrd /casper/initrd <enter><wait>",
    "boot <enter>"
  ]

  http_directory = var.autoinstall_dir
  http_port_min  = 8802
  http_port_max  = 8810

  communicator           = "ssh"
  ssh_username           = "mchasse"
  ssh_private_key_file   = "~/.ssh/id_ed25519"
  ssh_timeout            = "45m"
  ssh_handshake_attempts = 500

  template_description = "Ubuntu golden template — built by Packer"
}

build {
  name    = "ubuntu-golden"
  sources = ["source.proxmox-iso.ubuntu"]

  provisioner "shell" {
    script = "scripts/base-config.sh"
  }

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
