#!/bin/bash
# base-config.sh — Packer provisioner script
# Applies the same hardening as the base_server Ansible role.

set -euo pipefail

echo "==> Waiting for apt lock..."
while fuser /var/lib/dpkg/lock-frontend &>/dev/null; do sleep 2; done

echo "==> System update..."
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
sudo apt-get install -y -qq \
  btop glances iftop nethogs \
  unattended-upgrades apt-listchanges \
  jq tmux tree ncdu mtr-tiny

echo "==> SSH hardening..."
sudo tee /etc/ssh/sshd_config.d/99-hardening.conf > /dev/null << 'EOF'
# Xeronine SSH hardening baseline
PasswordAuthentication no
PermitRootLogin no
MaxAuthTries 3
MaxSessions 10
ClientAliveInterval 300
ClientAliveCountMax 2
X11Forwarding no
AllowTcpForwarding no
EOF

echo "==> JumpCloud PAM stub (agent installed by Ansible at deploy time)..."
sudo tee /etc/ssh/sshd_config.d/98-jumpcloud.conf > /dev/null << 'EOF'
# JumpCloud MFA support — enabled when agent is installed
# AuthenticationMethods publickey,keyboard-interactive publickey
# ChallengeResponseAuthentication yes
UsePAM yes
EOF

echo "==> Kernel hardening (sysctl)..."
sudo tee /etc/sysctl.d/99-hardening.conf > /dev/null << 'EOF'
# ASLR
kernel.randomize_va_space = 2
# IP spoofing protection
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
# Ignore ICMP redirects
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
# Disable IPv6
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
# Disable IP source routing
net.ipv4.conf.all.accept_source_route = 0
EOF
sudo sysctl --system -q

echo "==> UFW firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw --force enable

echo "==> Fail2ban..."
sudo tee /etc/fail2ban/jail.local > /dev/null << 'EOF'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
EOF
sudo systemctl enable fail2ban

echo "==> NFS common (for /mnt/backup mount at deploy time)..."
# Mount is configured by Ansible at deploy time, not baked into template

echo "==> Unattended security upgrades..."
sudo tee /etc/apt/apt.conf.d/50unattended-upgrades > /dev/null << 'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
};
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Packages "true";
EOF

sudo tee /etc/apt/apt.conf.d/20auto-upgrades > /dev/null << 'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

echo "==> Add NFS rocket mount stub to /etc/hosts..."
echo '10.200.99.15 rocket.xeronine.local' | sudo tee -a /etc/hosts

echo "==> Sudo nopasswd for mchasse..."
echo 'mchasse ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/mchasse
sudo chmod 440 /etc/sudoers.d/mchasse

echo "==> Timezone..."
sudo timedatectl set-timezone America/New_York

echo "==> Clean up apt..."
sudo apt-get autoremove -y -qq
sudo apt-get clean

echo "==> base-config.sh complete."
