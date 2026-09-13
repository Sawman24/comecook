#!/usr/bin/env bash
# ==============================================================================
# Cooked / ComeCook.app - 1-Command Server Update Script
# ==============================================================================

set -e

echo "🔄 Pulling latest code from GitHub and rebuilding containers..."
git pull origin main
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps

echo "✓ Update complete and server healthy!"
