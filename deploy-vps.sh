#!/bin/bash
# GitOps deploy: pull vps-config and apply Caddy changes
set -e
cd /home/mjb/projects/vps-config
git pull origin main
sudo cp caddy/Caddyfile /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
echo "[$(date)] deploy ok" >> /home/mjb/deploy.log
