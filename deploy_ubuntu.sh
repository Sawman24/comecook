#!/usr/bin/env bash
# ==============================================================================
# Cooked / ComeCook.app - Ubuntu Automated Production Deployment Script
# ==============================================================================

set -e

echo "🍳 Starting Cooked (ComeCook.app) deployment on Ubuntu..."

# 1. Ensure curl and git are installed
echo "📦 Step 1: Checking system packages..."
sudo apt update -y
sudo apt install -y curl git openssl

# 2. Check and Install Docker / Docker Compose if missing
if ! command -v docker &> /dev/null; then
    echo "🐳 Docker not found. Installing Docker Engine..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo "✓ Docker installed successfully."
else
    echo "✓ Docker is already installed."
fi

# 3. Configure UFW Firewall (Allow SSH, HTTP, HTTPS)
echo "🛡️ Step 2: Configuring UFW Firewall..."
if command -v ufw &> /dev/null; then
    sudo ufw allow OpenSSH || sudo ufw allow 22/tcp || true
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    echo "✓ Firewall rules configured (Ports 22, 80, 443 allowed)."
fi

# 4. Generate .env file if not present
echo "⚙️ Step 3: Configuring Environment..."
if [ ! -f .env ]; then
    echo "Creating new .env file from template..."
    cp .env.example .env
    
    # Generate random 64-character hex key
    RAND_SECRET=$(openssl rand -hex 32)
    sed -i "s/replace_with_a_secure_random_64_char_hex_key/$RAND_SECRET/" .env
    echo "✓ Generated cryptographically secure SECRET_KEY."
else
    echo "✓ Existing .env file found."
fi

# 5. Build and Launch Containers
echo "🚀 Step 4: Building and launching production containers with automated HTTPS..."
docker compose -f docker-compose.prod.yml up -d --build

# 6. Verify Healthcheck
echo "🩺 Step 5: Waiting for container healthcheck..."
sleep 5
docker compose -f docker-compose.prod.yml ps

echo ""
echo "=============================================================================="
echo "🎉 DEPLOYMENT COMPLETE!"
echo "=============================================================================="
echo "🌐 Your Cooked platform is now running live!"
echo "🔒 HTTPS Encryption: Automated Let's Encrypt certificates managed by Caddy."
echo ""
echo "👉 NEXT STEPS:"
echo "1. Ensure your DNS A-Record for comecook.app points to this server's public IP."
echo "2. Open https://comecook.app in your browser."
echo "3. Click 'Join the Kitchen' / Register to create your account."
echo "   ⭐️ The very first account registered will automatically become the OWNER / ADMIN!"
echo "=============================================================================="
