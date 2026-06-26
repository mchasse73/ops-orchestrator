#!/bin/bash
# install.sh — deploy ops-orchestrator on a fresh Ubuntu server
# Run as mchasse with sudo access on the target server.
# Reads credentials from Vault (requires VAULT_ADDR + VAULT_TOKEN set).
set -euo pipefail

OPS_DIR="/opt/ops-orchestrator"
ENV_FILE="/etc/ops-orchestrator/env"
REPO="https://github.com/mchasse73/ops-orchestrator.git"
OLLAMA_URL="${OLLAMA_URL:-http://ai.xeronine.local}"

echo "==> Installing ops-orchestrator on $(hostname)..."

# 1) System dependencies
sudo apt-get update -qq
sudo apt-get install -y -qq git python3 python3-pip python3-venv sshpass

# 2) Clone / update repo
if [ -d "$OPS_DIR/.git" ]; then
  echo "==> Updating existing repo..."
  git -C "$OPS_DIR" pull --ff-only
else
  echo "==> Cloning repo..."
  sudo git clone "$REPO" "$OPS_DIR"
  sudo chown -R mchasse:mchasse "$OPS_DIR"
fi

# 3) Python venv + dependencies
cd "$OPS_DIR"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
.venv/bin/pip install -q uvicorn fastapi httpx

# 4) Fetch credentials from Vault
echo "==> Fetching credentials from Vault..."
PROXMOX_HOST=$(vault kv get -field=api_host_1 secret/proxmox)
PROXMOX_PASSWORD=$(vault kv get -field=password secret/proxmox)
PROXMOX_USER=$(vault kv get -field=username secret/proxmox)
TECHNITIUM_TOKEN=$(vault kv get -field=ns1_token secret/technitium/api)
TECHNITIUM_URL=$(vault kv get -field=ns1_url secret/technitium/api 2>/dev/null || echo "https://10.200.99.2")
ANTHROPIC_API_KEY=$(vault kv get -field=api_key secret/anthropic 2>/dev/null || echo "")

# Generate API key for the ops service
OPS_API_KEY=$(vault kv get -field=api_key secret/ops-orchestrator/api-key 2>/dev/null || \
  python3 -c "import secrets; k=secrets.token_urlsafe(32); print(k)" | tee /tmp/ops_key.tmp)
if [ -f /tmp/ops_key.tmp ]; then
  NEW_KEY=$(cat /tmp/ops_key.tmp)
  vault kv put secret/ops-orchestrator/api-key api_key="$NEW_KEY"
  rm /tmp/ops_key.tmp
  OPS_API_KEY="$NEW_KEY"
fi

# 5) Write env file
sudo mkdir -p /etc/ops-orchestrator
sudo tee "$ENV_FILE" > /dev/null << ENVEOF
# ops-orchestrator environment — managed by install.sh, do not edit manually
OPS_API_KEY=${OPS_API_KEY}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
PROXMOX_PASSWORD=${PROXMOX_PASSWORD}
PROXMOX_HOST=${PROXMOX_HOST}
PROXMOX_USER=${PROXMOX_USER}
TECHNITIUM_TOKEN=${TECHNITIUM_TOKEN}
VAULT_ADDR=${VAULT_ADDR}
VAULT_NAMESPACE=admin
VAULT_SKIP_VERIFY=true
VAULT_TOKEN=${VAULT_TOKEN}
ENVEOF
sudo chmod 600 "$ENV_FILE"
sudo chown root:mchasse "$ENV_FILE"

# 6) Write config.yaml
cat > "$OPS_DIR/config.yaml" << CFGEOF
models:
  coordinator: claude-sonnet-4-6
  worker: claude-haiku-4-5

ollama_url: "${OLLAMA_URL}:11434"
ollama_model: "qwen3:32b"
ollama_timeout: 120

skills_dir: skills
defer_tools: false
confirm_destructive: true

mempalace_url: "http://beast.xeronine.local:8766/mcp"
mempalace_wing: "ops_central"

mcp_servers:
  - name: proxmox
    command: ["python", "-m", "mcp_servers.proxmox.server"]
    env:
      PROXMOX_HOST: "${PROXMOX_HOST}"
      PROXMOX_USER: "root@pam"
  - name: technitium
    command: ["python", "-m", "mcp_servers.technitium.server"]
    env:
      TECHNITIUM_URL: "${TECHNITIUM_URL}"
      TECHNITIUM_TOKEN_ENV: TECHNITIUM_TOKEN
  - name: dynu
    command: ["python", "-m", "mcp_servers.dynu.server"]
    env:
      DYNU_API_KEY_ENV: DYNU_API_KEY
CFGEOF
chmod 640 "$OPS_DIR/config.yaml"

# 7) Install + enable systemd service
sudo cp "$OPS_DIR/deploy/ops-orchestrator.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ops-orchestrator
sudo systemctl restart ops-orchestrator

# 8) Open UFW port
sudo ufw allow from 10.200.0.0/16 to any port 8080 proto tcp comment "ops-orchestrator API"

echo ""
echo "==> ops-orchestrator deployed on $(hostname)"
echo "    API: http://$(hostname -I | awk '{print $1}'):8080"
echo "    Health: curl http://$(hostname -I | awk '{print $1}'):8080/health"
echo "    API Key: stored in Vault at secret/ops-orchestrator/api-key"
echo ""
echo "From any machine on the network:"
echo "    export OPS_SERVER=http://$(hostname -f):8080"
echo "    export OPS_API_KEY=\$(vault kv get -field=api_key secret/ops-orchestrator/api-key)"
echo "    ops-remote 'list all VMs'"
