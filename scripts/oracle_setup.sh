#!/bin/bash
# =============================================================================
# RoughCut (ChannelDNA) 24/7 Oracle Cloud Always-Free Server Setup Script
# =============================================================================

set -e

echo "=== [1/5] Updating OS packages and installing dependencies ==="
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg unzip curl

echo "=== [2/5] Extracting deployment bundle ==="
mkdir -p ~/roughcut_bot
unzip -o oracle_cloud_bundle.zip -d ~/roughcut_bot
cd ~/roughcut_bot

echo "=== [3/5] Setting up Python Virtual Environment ==="
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt discord.py modal

echo "=== [4/5] Configuring Modal GPU Cloud Authentication ==="
modal token set --token-id "ak-FkEQy9BJkBw1461Ilh0MyN" --token-secret "as-aEuTPFrqSBlMLQtkeZakXf"

echo "=== [5/5] Registering 24/7 systemd auto-restart service ==="
CURRENT_USER=$(whoami)
APP_DIR=$(pwd)

sudo bash -c "cat <<EOF > /etc/systemd/system/roughcut.service
[Unit]
Description=RoughCut 24/7 Discord Bot Automation
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/python3 -m bot.discord_bot
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=USE_MODAL_CLOUD=1

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable roughcut.service
sudo systemctl restart roughcut.service

echo "================================================================"
echo "🎉 RoughCut Bot is now successfully running 24/7 as a system service!"
echo "• Status check: sudo systemctl status roughcut"
echo "• Live logs:    sudo journalctl -u roughcut -f"
echo "• Restart:      sudo systemctl restart roughcut"
echo "• Stop:         sudo systemctl stop roughcut"
echo "================================================================"
