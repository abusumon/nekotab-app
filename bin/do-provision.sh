#!/usr/bin/env bash
# bin/do-provision.sh — One-time setup for a fresh DigitalOcean Droplet
#
# Run this script AS ROOT on a freshly created Ubuntu 22.04/24.04 Droplet.
# After provisioning, all subsequent deploys happen automatically via GitHub Actions.
#
# Usage:
#   ssh root@YOUR_DROPLET_IP
#   curl -sSL https://raw.githubusercontent.com/YOUR_REPO/main/bin/do-provision.sh | bash
#   — OR —
#   scp bin/do-provision.sh root@YOUR_DROPLET_IP:/tmp/
#   ssh root@YOUR_DROPLET_IP bash /tmp/do-provision.sh
#
# After provisioning:
#   1. Copy your .env file:   scp .env.do.example root@DROPLET:/opt/nekotab/.env  (then edit it)
#   2. Add the deploy SSH key public key to /home/nekotab/.ssh/authorized_keys
#   3. Add the following GitHub repository secrets (Settings → Secrets → Actions):
#        DO_API_TOKEN        — DO personal access token with registry write access
#        DO_REGISTRY_NAME    — e.g.  nekotab-registry
#        DO_DROPLET_IP       — this Droplet's public IP
#        DO_SSH_PRIVATE_KEY  — private key for the deploy key pair
#   4. Push to main or trigger the workflow manually.

set -euo pipefail

DEPLOY_USER="nekotab"
APP_DIR="/opt/nekotab"

echo "============================================================"
echo "  NekoTab — DigitalOcean Droplet Provisioner"
echo "============================================================"

# ---------------------------------------------------------------------------
# System update
# ---------------------------------------------------------------------------
echo "--> Updating packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git unzip ca-certificates gnupg lsb-release \
    ufw fail2ban htop

# ---------------------------------------------------------------------------
# Docker (official repo)
# ---------------------------------------------------------------------------
echo "--> Installing Docker..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Enable and start Docker
systemctl enable docker
systemctl start docker

# ---------------------------------------------------------------------------
# doctl (DigitalOcean CLI) — used for registry auth on the Droplet
# ---------------------------------------------------------------------------
echo "--> Installing doctl..."
DOCTL_VER=$(curl -s https://api.github.com/repos/digitalocean/doctl/releases/latest \
    | grep '"tag_name"' | sed -E 's/.*"v([^"]+)".*/\1/')
curl -sSL "https://github.com/digitalocean/doctl/releases/download/v${DOCTL_VER}/doctl-${DOCTL_VER}-linux-amd64.tar.gz" \
    | tar xz -C /usr/local/bin

# ---------------------------------------------------------------------------
# Deploy user
# ---------------------------------------------------------------------------
echo "--> Creating deploy user: $DEPLOY_USER..."
if ! id "$DEPLOY_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"

# SSH directory for deploy key
mkdir -p "/home/$DEPLOY_USER/.ssh"
chmod 700 "/home/$DEPLOY_USER/.ssh"
touch "/home/$DEPLOY_USER/.ssh/authorized_keys"
chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"

# ---------------------------------------------------------------------------
# Application directory
# ---------------------------------------------------------------------------
echo "--> Creating app directory: $APP_DIR..."
mkdir -p "$APP_DIR/config" "$APP_DIR/bin"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"

# ---------------------------------------------------------------------------
# Firewall (UFW)
# Allow SSH (22), HTTP (80), HTTPS (443).
# The DO Load Balancer connects to port 80; the Droplet never needs 443 open
# since TLS terminates at the LB.  Keep 443 open for direct certbot fallback.
# ---------------------------------------------------------------------------
echo "--> Configuring UFW firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   comment "SSH"
ufw allow 80/tcp   comment "HTTP (DO Load Balancer)"
ufw allow 443/tcp  comment "HTTPS (direct / certbot fallback)"
ufw --force enable

# ---------------------------------------------------------------------------
# Docker log rotation (prevent /var/lib/docker/containers from filling disk)
# ---------------------------------------------------------------------------
echo "--> Configuring Docker log rotation..."
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "5"
  }
}
EOF
systemctl reload docker

# ---------------------------------------------------------------------------
# Fail2ban (basic SSH brute-force protection)
# ---------------------------------------------------------------------------
echo "--> Enabling fail2ban..."
systemctl enable fail2ban
systemctl start fail2ban

# ---------------------------------------------------------------------------
# Swap (safety net — 4 GiB Droplet can hit OOM during peak tournament rounds)
# ---------------------------------------------------------------------------
if [ ! -f /swapfile ]; then
    echo "--> Creating 2 GiB swap..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
    sysctl -p
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  Provisioning complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "  1. Copy and fill in your env file:"
echo "       scp .env.do.example $DEPLOY_USER@\$(hostname -I | awk '{print \$1}'):/opt/nekotab/.env"
echo "       ssh $DEPLOY_USER@\$(hostname -I | awk '{print \$1}') nano /opt/nekotab/.env"
echo ""
echo "  2. Add the GitHub Actions deploy SSH public key to:"
echo "       /home/$DEPLOY_USER/.ssh/authorized_keys"
echo ""
echo "  3. Add GitHub repository secrets:"
echo "       DO_API_TOKEN      — DO API token with registry access"
echo "       DO_REGISTRY_NAME  — your DO Container Registry name"
echo "       DO_DROPLET_IP     — $(hostname -I | awk '{print $1}')"
echo "       DO_SSH_PRIVATE_KEY — private key for the deploy key pair"
echo ""
echo "  4. Point *.nekotab.app DNS A records to this IP:"
echo "       IP: $(hostname -I | awk '{print $1}')"
echo "       (Use a DO Load Balancer in front for managed TLS)"
echo ""
echo "  5. Push to main or trigger the workflow manually to deploy."
echo ""
