#!/bin/sh
# One-time VM preparation (Debian/Ubuntu on Compute Engine): Docker Engine + compose plugin + swap.
set -eu
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER" || true
# swap: Manim + LaTeX renders spike memory; swap keeps the OOM killer away
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 4G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi
docker compose version || sudo docker compose version
