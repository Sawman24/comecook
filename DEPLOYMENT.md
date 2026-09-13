# 🚀 Cooked - Production Deployment Guide (Linux + Docker + HTTPS)

This guide walks you through deploying **Cooked** to a Linux server (Ubuntu/Debian, Fedora, CentOS/RHEL, Alpine, etc.) using Docker, Docker Compose, and automated HTTPS encryption.

---

## 📋 Table of Contents
1. [Initial Server Requirements](#1-initial-server-requirements)
2. [Pushing to GitHub & Cloning on Server](#2-pushing-to-github--cloning-on-server)
3. [Environment Configuration (`.env`)](#3-environment-configuration-env)
4. [Deploying with Docker Compose](#4-deploying-with-docker-compose)
   - [Option A: Production with Automatic HTTPS (Recommended)](#option-a-production-with-automatic-https-recommended)
   - [Option B: Standalone Container (Behind Custom Nginx/Cloudflare)](#option-b-standalone-container-behind-custom-nginxcloudflare)
5. [Registering the Owner / Admin Account](#5-registering-the-owner--admin-account)
6. [Data Persistence & Backups](#6-data-persistence--backups)
7. [Useful Maintenance Commands](#7-useful-maintenance-commands)

---

## 1. Initial Server Requirements

Ensure your Linux server has Docker and Docker Compose installed:

```bash
# Ubuntu / Debian install script
sudo apt update && sudo apt install -y curl git
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

Verify installation:
```bash
docker --version
docker compose version
```

---

## 2. Pushing to GitHub & Cloning on Server

### A. Push from your local machine to GitHub:
```bash
git init
git add .
git commit -m "Initial Cooked production commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/Cooked.git
git push -u origin main
```

### B. Clone on your Linux server:
```bash
git clone https://github.com/YOUR_USERNAME/Cooked.git
cd Cooked
```

---

## 3. Environment Configuration (`.env`)

Copy the environment template and generate a cryptographically secure `SECRET_KEY`:

```bash
cp .env.example .env
```

Generate a secure key and update `.env`:
```bash
# Generate key
openssl rand -hex 32
```

Edit `.env` using your preferred editor (`nano .env` or `vim .env`):
```ini
COOKED_ENV=production
SECRET_KEY=YOUR_GENERATED_64_CHAR_HEX_KEY
PORT=5050
DOMAIN=cooked.yourdomain.com
SESSION_COOKIE_SECURE=1
COOKED_SEED_DEMO=0
```

---

## 4. Deploying with Docker Compose

### Option A: Production with Automatic HTTPS (Recommended)
This uses Caddy alongside Cooked to automatically provision and renew valid **Let's Encrypt SSL Certificates** on ports 80 & 443 with zero configuration.

1. Ensure your DNS A-Record (`cooked.yourdomain.com`) points to your server's public IP address.
2. Ensure firewall ports `80` and `443` are open (`sudo ufw allow 80/tcp && sudo ufw allow 443/tcp`).
3. Start the containers:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
4. View live logs:
```bash
docker compose -f docker-compose.prod.yml logs -f
```

---

### Option B: Standalone Container (Behind Custom Nginx/Cloudflare)
If you already run an existing Nginx / Traefik reverse proxy or Cloudflare tunnel on your host:

```bash
docker compose up -d --build
```
Your app will be accessible locally on `http://127.0.0.1:5050` with healthcheck endpoint at `http://127.0.0.1:5050/api/health`.

---

## 5. Registering the Owner / Admin Account

> [!IMPORTANT]
> **First-User Owner Guarantee**:
> The database is clean and contains 0 users. The **very first user to register** on your live instance automatically and permanently receives **Owner / Administrator (`is_admin: 1`)** permissions.

1. Open `https://cooked.yourdomain.com` in your browser.
2. Click **"Join the Kitchen"** / **Register**.
3. Create your account:
   - Pick your desired Executive Chef username (e.g. `headchef` or your own name).
   - Enter your email and a strong password (8+ chars, upper, lower, number, symbol).
4. Upon clicking Register, your account will be granted full administrative authority. You will see the **Admin Command Center** in your navigation bar to manage reported content, moderate posts, and oversee all kitchen stations.

---

## 6. Data Persistence & Backups

All persistent data is stored in Docker named volumes:
- **`cooked-data`**: Holds the SQLite database file (`/app/data/cooked.db`).
- **`cooked-uploads`**: Holds all user dish photo uploads (`/app/uploads/`).

### Create an Instant Backup:
```bash
# Backup SQLite database
docker exec -t cooked-app sqlite3 /app/data/cooked.db ".backup '/app/data/backup_$(date +%Y%m%d_%H%M%S).db'"

# Copy backup to host
docker cp cooked-app:/app/data/ ./backups/
```

---

## 7. Useful Maintenance Commands

```bash
# Check container health & status
docker compose -f docker-compose.prod.yml ps

# View live application logs
docker compose -f docker-compose.prod.yml logs -f cooked-app

# Restart application
docker compose -f docker-compose.prod.yml restart cooked-app

# Pull updates from GitHub and rebuild
git pull origin main
docker compose -f docker-compose.prod.yml up -d --build

# Wipe database and reset to 0 users (clean slate)
docker exec -it cooked-app python reset_db.py
```
