"""Configuration for ChannelDNA Discord Automation Bot."""

import os
from pathlib import Path

# Discord Bot Token (Set via environment variable or fill in below)
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "MTU0MTQ3NTQ0Mzc2NzY0ODM3Nw.GjfrOM.tT1KRMZVa8eqrVJ9uaNGUvDDK1Hz_HVt3MItLk")

# Primary Administrator Discord User ID (Integer)
# Only this User ID can execute /암호발급, /현황, /해지
ADMIN_USER_ID = int(os.environ.get("DISCORD_ADMIN_USER_ID", "584210962182176769"))

# Chzzk Background Polling Interval (in seconds)
CHZZK_POLL_INTERVAL_SEC = 120.0  # 2 minutes

# Minimum VOD length to trigger rough cut export (in seconds)
# Excludes test broadcasts under 20 minutes
MIN_VOD_DURATION_SEC = 1200  # 20 minutes

# Cloud vs Local Pipeline Engine (Default: True with NVIDIA L4 GPU)
USE_MODAL_CLOUD = os.environ.get("USE_MODAL_CLOUD", "1").lower() in ("1", "true")
