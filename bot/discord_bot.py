"""ChannelDNA 24/7 Chzzk Monitoring & Automatic Rough Cut Delivery Discord Bot."""

import asyncio
import io
import datetime
import os
import random
import socket
import string
import sys
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def acquire_singleton_lock() -> bool:
    global _lock_socket
    # Only enforce strict socket lock on local Windows desktop
    if sys.platform != "win32":
        return True
    _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _lock_socket.bind(("127.0.0.1", 49151))
        return True
    except socket.error:
        print("[WARN] Another local instance may be active, proceeding in serverless mode...", flush=True)
        return True

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from bot import config
from channel_dna.core.chzzk_client import (
    extract_chzzk_channel_id,
    extract_chzzk_video_no,
    fetch_chzzk_video_meta,
    fetch_chzzk_vod_list,
)
from channel_dna.core.db import DBManager

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
db = DBManager()


def generate_secure_passcode(prefix: str = "CDNA") -> str:
    """Generates an 8-character secure single-use passcode (e.g. YMDU-8492)."""
    clean_prefix = "".join(c for c in prefix if c.isalnum())[:4].upper()
    if not clean_prefix:
        clean_prefix = "CDNA"
    rand_chars = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{clean_prefix}-{rand_chars}"


from aiohttp import web

ADMIN_SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY", "channeldna-secret-admin-key-2026")


async def handle_health(request):
    return web.Response(text="RoughCut Discord Bot 24/7 is Live!", headers={"Access-Control-Allow-Origin": "*"})


async def handle_options(request):
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
    )


async def handle_sync_profile(request):
    try:
        data = await request.json()
        secret = data.get("secret_key", "")
        if secret != ADMIN_SECRET_KEY:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=401, headers={"Access-Control-Allow-Origin": "*"})

        profile_data = data.get("profile")
        if not profile_data:
            return web.json_response({"success": False, "error": "Missing profile data"}, status=400, headers={"Access-Control-Allow-Origin": "*"})

        from channel_dna.core.models import ChannelProfile
        prof = ChannelProfile.from_dict(profile_data)
        db.save_profile(prof)
        print(f"[Cloud Profile Synced] Saved '{prof.channel_name}' ({prof.profile_type}) to Render DB.")
        return web.json_response({"success": True, "profile_id": prof.profile_id}, headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500, headers={"Access-Control-Allow-Origin": "*"})


async def handle_issue_passcode(request):
    try:
        data = await request.json()
        secret = data.get("secret_key", "")
        if secret != ADMIN_SECRET_KEY:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=401, headers={"Access-Control-Allow-Origin": "*"})

        ch_id = data.get("channel_id")
        st_name = data.get("streamer_name")
        passcode = data.get("passcode")
        target_dna = data.get("target_dna_profile") or st_name

        if not ch_id or not st_name or not passcode:
            return web.json_response({"success": False, "error": "Missing parameters"}, status=400, headers={"Access-Control-Allow-Origin": "*"})

        db.create_passcode_binding(
            channel_id=ch_id,
            streamer_name=st_name,
            passcode=passcode,
            target_dna_profile=target_dna,
        )
        print(f"[Cloud Binding Synced] Registered '{st_name}' ({ch_id}, passcode: {passcode}) on Render DB.")
        return web.json_response({"success": True, "passcode": passcode}, headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500, headers={"Access-Control-Allow-Origin": "*"})


async def handle_unbind_streamer(request):
    try:
        data = await request.json()
        secret = data.get("secret_key", "")
        if secret != ADMIN_SECRET_KEY:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=401, headers={"Access-Control-Allow-Origin": "*"})

        target = data.get("streamer_name") or data.get("channel_id")
        if not target:
            return web.json_response({"success": False, "error": "Missing target"}, status=400, headers={"Access-Control-Allow-Origin": "*"})

        res = db.unbind_streamer(target)
        return web.json_response({"success": res}, headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500, headers={"Access-Control-Allow-Origin": "*"})


async def handle_list_profiles(request):
    try:
        with db._session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT profile_id, channel_name, avg_shot_length, tension_interval, silence_tolerance, highlight_rms_threshold, profile_type, youtube_url, chzzk_url, updated_at FROM channel_profiles;")
            rows = cur.fetchall()
            profiles = [dict(r) for r in rows]

            cur.execute("SELECT channel_id, streamer_name, target_dna_profile, passcode, is_bound, created_at, bound_at FROM streamer_bindings;")
            b_rows = cur.fetchall()
            bindings = [dict(b) for b in b_rows]

        return web.json_response({"success": True, "profiles": profiles, "bindings": bindings}, headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500, headers={"Access-Control-Allow-Origin": "*"})


async def handle_add_credit(request):
    """External Webhook API for automated credit charging upon web payment."""
    try:
        data = await request.json()
        secret = data.get("secret_key", "")
        if secret != ADMIN_SECRET_KEY:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=401, headers={"Access-Control-Allow-Origin": "*"})

        user_id = data.get("discord_user_id")
        amount = data.get("amount", 0)
        order_id = data.get("order_id", "")
        reason = data.get("reason", "웹 결제 충전")

        if not user_id or amount <= 0:
            return web.json_response({"success": False, "error": "Invalid user_id or amount"}, status=400, headers={"Access-Control-Allow-Origin": "*"})

        new_bal = db.add_user_credits(int(user_id), int(amount), reason=reason, order_id=order_id)
        return web.json_response(
            {"success": True, "discord_user_id": user_id, "added_credits": amount, "current_balance": new_bal},
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500, headers={"Access-Control-Allow-Origin": "*"})


async def handle_payapp_webhook(request):
    """External Webhook API for PayApp automated payment integration."""
    try:
        data = await request.post()
        state = data.get("state", "")
        price = data.get("price", "0")
        discord_user_id = data.get("var1", "")
        mul_no = data.get("mul_no", "")

        # PayApp state '4' typically means successful payment
        if state == "4" and discord_user_id.isdigit():
            # Conversion: 3000 KRW = 1 Credit
            amount = int(float(price))
            credits_to_add = amount // 3000
            
            if credits_to_add > 0:
                new_bal = db.add_user_credits(
                    int(discord_user_id), 
                    credits_to_add, 
                    reason=f"PayApp 웹 결제 ({amount}원)", 
                    order_id=mul_no
                )
                print(f"[PayApp] Successfully added {credits_to_add} credits to user {discord_user_id}. Order: {mul_no}")
        
        # PayApp requires a simple text response like 'SUCCESS'
        return web.Response(text="SUCCESS")
    except Exception as e:
        print(f"[PayApp Webhook Error] {e}")
        return web.Response(text="FAIL", status=500)


async def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    app = web.Application()
    app.router.add_route("OPTIONS", "/{tail:.*}", handle_options)
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/list_profiles", handle_list_profiles)
    app.router.add_post("/api/sync_profile", handle_sync_profile)
    app.router.add_post("/api/issue_passcode", handle_issue_passcode)
    app.router.add_post("/api/unbind_streamer", handle_unbind_streamer)
    app.router.add_post("/api/credit/add", handle_add_credit)
    app.router.add_post("/api/payapp/webhook", handle_payapp_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[OK] Health check and Cloud Sync API server listening on port {port}")


# =============================================================================
# Bot Lifecycle Events & Message Queue
# =============================================================================

import dataclasses

@dataclasses.dataclass
class OutboundMessage:
    user_id: int
    content: str
    files: list[discord.File]

outbound_queue: asyncio.Queue[OutboundMessage] = asyncio.Queue()

async def outbound_worker():
    """Processes the outbound message queue sequentially to prevent Discord 429 Rate Limits."""
    while True:
        msg = await outbound_queue.get()
        try:
            user = await bot.fetch_user(msg.user_id)
            if user:
                await user.send(content=msg.content, files=msg.files)
                print(f"[OK] Successfully delivered package to Discord User: {msg.user_id}")
        except Exception as e:
            print(f"[WARN] Failed to deliver package to user {msg.user_id}: {e}")
        finally:
            outbound_queue.task_done()
            await asyncio.sleep(1.5)  # Safe rate limit interval (1.5 seconds)


@bot.event
async def on_ready():
    print(f"[OK] RoughCut Discord Bot logged in as: {bot.user} (ID: {bot.user.id})")

    try:
        synced = await bot.tree.sync()
        print(f"[OK] Synced {len(synced)} slash commands globally.")
    except Exception as e:
        print(f"[WARN] Slash command sync warning: {e}")

    # Start the outbound message queue worker
    bot.loop.create_task(outbound_worker())

    if not chzzk_watcher_loop.is_running():
        chzzk_watcher_loop.start()
        print("[OK] 24/7 Chzzk VOD Watcher loop started.")


# =============================================================================
# Admin Slash Commands (Restricted to ADMIN_USER_ID)
# =============================================================================


# =============================================================================
# Admin Slash Commands (Local GUI is primary, Status/Unbind only)
# =============================================================================


# =============================================================================
# Admin Slash Commands (Restricted & Hidden from Regular Users)
# =============================================================================


@bot.tree.command(
    name="현황",
    description="[관리자] 현재 등록된 스트리머 모니터링 및 인증 바인딩 현황을 조회합니다.",
)
@app_commands.default_permissions(administrator=True)
async def cmd_status(interaction: discord.Interaction):
    if config.ADMIN_USER_ID != 0 and interaction.user.id != config.ADMIN_USER_ID:
        await interaction.response.send_message(
            "❌ 관리자만 실행할 수 있는 명령어입니다.", ephemeral=True
        )
        return

    bindings = db.get_all_streamer_bindings()
    if not bindings:
        await interaction.response.send_message(
            "등록된 스트리머 채널이 없습니다.", ephemeral=True
        )
        return

    lines = ["[스트리머 모니터링 현황]"]
    for b in bindings:
        st_name = b.get("streamer_name", "미지정")
        ch_id = b.get("channel_id", "")
        is_bound = b.get("is_bound", 0)
        discord_id = b.get("master_discord_id") or "미인증"
        passcode = b.get("passcode") or "폐기완료"
        last_vod = b.get("last_processed_video_no") or "없음"

        status_str = f"인증완료 (수신자: {discord_id})" if is_bound else f"대기중 (암호: {passcode})"
        lines.append(f"• {st_name} ({ch_id[:8]}...): {status_str} | 최근VOD: {last_vod}")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(
    name="해지",
    description="[관리자] 특정 스트리머의 모니터링 및 파일 자동 전송을 해지합니다.",
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(스트리머="해지할 스트리머 이름 또는 채널 ID")
async def cmd_unbind(interaction: discord.Interaction, 스트리머: str):
    if config.ADMIN_USER_ID != 0 and interaction.user.id != config.ADMIN_USER_ID:
        await interaction.response.send_message(
            "❌ 관리자만 실행할 수 있는 명령어입니다.", ephemeral=True
        )
        return

    success = db.unbind_streamer(스트리머)
    if success:
        await interaction.response.send_message(
            f"✓ [{스트리머}] 모니터링 및 바인딩이 정상 해지되었습니다.", ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"❌ [{스트리머}] 대상을 찾을 수 없습니다.", ephemeral=True
        )


@bot.tree.command(
    name="크레딧지급",
    description="[관리자] 특정 사용자에게 가편집 크레딧을 수동 지급합니다.",
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(대상유저="크레딧을 지급할 디스코드 유저", 수량="지급할 크레딧 수량", 사유="지급 사유")
async def cmd_give_credit(interaction: discord.Interaction, 대상유저: discord.User, 수량: int, 사유: str = "관리자 수동 지급"):
    if config.ADMIN_USER_ID != 0 and interaction.user.id != config.ADMIN_USER_ID:
        await interaction.response.send_message("❌ 관리자만 실행할 수 있는 명령어입니다.", ephemeral=True)
        return
    if 수량 <= 0:
        await interaction.response.send_message("❌ 수량은 1 이상이어야 합니다.", ephemeral=True)
        return

    new_bal = db.add_user_credits(대상유저.id, 수량, reason=사유)
    await interaction.response.send_message(
        f"✅ **[{대상유저.display_name}]** 님에게 `{수량}` 크레딧 지급 완료! (현재 잔액: `{new_bal}`개)",
        ephemeral=True,
    )


@bot.tree.command(
    name="크레딧차감",
    description="[관리자] 특정 사용자의 가편집 크레딧을 수동 차감합니다.",
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(대상유저="크레딧을 차감할 디스코드 유저", 수량="차감할 크레딧 수량", 사유="차감 사유")
async def cmd_deduct_credit(interaction: discord.Interaction, 대상유저: discord.User, 수량: int, 사유: str = "관리자 수동 차감"):
    if config.ADMIN_USER_ID != 0 and interaction.user.id != config.ADMIN_USER_ID:
        await interaction.response.send_message("❌ 관리자만 실행할 수 있는 명령어입니다.", ephemeral=True)
        return
    if 수량 <= 0:
        await interaction.response.send_message("❌ 수량은 1 이상이어야 합니다.", ephemeral=True)
        return

    success, new_bal = db.deduct_user_credit(대상유저.id, reason=사유)
    if not success:
        await interaction.response.send_message(f"❌ 잔액이 부족합니다. (현재 잔액: `{new_bal}`개)", ephemeral=True)
        return
    await interaction.response.send_message(
        f"✅ **[{대상유저.display_name}]** 님의 크레딧 1개 차감 완료! (현재 잔액: `{new_bal}`개)",
        ephemeral=True,
    )


# =============================================================================
# Modal for 3+3 YouTube Profile Calibration
# =============================================================================


class ProfileRegistrationModal(discord.ui.Modal, title="새 스트리머 발화 프로필 등록 (3+3 분석)"):
    profile_name_input = discord.ui.TextInput(
        label="프로필 이름 (식별용 라벨)",
        placeholder="예: 하이텐션 게임 방송 스타일, 잔잔 토크 스타일",
        max_length=50,
        required=True,
    )
    chzzk_url_input = discord.ui.TextInput(
        label="치지직 채널 주소 (선택 입력)",
        placeholder="https://chzzk.naver.com/...",
        required=False,
    )
    solo_links_input = discord.ui.TextInput(
        label="🎤 솔로 방송 유튜브 링크 3개 (줄바꿈 구분)",
        style=discord.TextStyle.paragraph,
        placeholder="https://youtube.com/watch?v=...\nhttps://youtube.com/watch?v=...\nhttps://youtube.com/watch?v=...",
        required=True,
    )
    collab_links_input = discord.ui.TextInput(
        label="👥 합방/콜라보 유튜브 링크 3개 (줄바꿈 구분)",
        style=discord.TextStyle.paragraph,
        placeholder="https://youtube.com/watch?v=...\nhttps://youtube.com/watch?v=...\nhttps://youtube.com/watch?v=...",
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        p_name = self.profile_name_input.value.strip()
        ch_url = self.chzzk_url_input.value.strip()
        solo_urls = [u.strip() for u in self.solo_links_input.value.split("\n") if u.strip()]
        collab_urls = [u.strip() for u in self.collab_links_input.value.split("\n") if u.strip()]

        from channel_dna.core.profiler import ChannelProfiler
        profiler = ChannelProfiler(db=db)
        res = profiler.calibrate_from_video_urls(
            solo_urls=solo_urls,
            collab_urls=collab_urls,
            profile_name=p_name,
            chzzk_channel_url=ch_url,
            discord_user_id=interaction.user.id,
        )

        await interaction.followup.send(
            f"✅ **발화 프로필 등록 완료!**\n"
            f"• **프로필 이름:** `{p_name}`\n"
            f"• **솔로 ASL:** `{res['solo_profile']['avg_shot_length']}s` / 무음 기준: `{res['solo_profile']['silence_tolerance']}s`\n"
            f"• **합방 ASL:** `{res['collab_profile']['avg_shot_length']}s` / 무음 기준: `{res['collab_profile']['silence_tolerance']}s`\n"
            f"*(입력하신 6개 유튜브 링크는 음향 특성 산출 후 즉시 폐기되었습니다)*\n\n"
            f"👉 이제 `/가편집` 명령어를 실행할 때 해당 프로필을 선택하여 가편집을 진행하실 수 있습니다.",
            ephemeral=True,
        )


# =============================================================================
# 2-Step Interaction: Profile Dropdown + Mode Selection View
# =============================================================================


class ProfileSelectDropdown(discord.ui.Select):
    def __init__(self, profiles: list[dict[str, Any]], parent_view: Any):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label=p["profile_name"][:100],
                value=p["profile_id"],
                description=f"솔로 ASL {p.get('solo_profile', {}).get('avg_shot_length', 3.8)}s / 합방 ASL {p.get('collab_profile', {}).get('avg_shot_length', 2.2)}s",
            )
            for p in profiles[:25]
        ]
        super().__init__(placeholder="🎯 적용할 스트리머 발화 프로필을 선택하세요", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.discord_user_id:
            await interaction.response.send_message("❌ 본인의 요청에서만 선택할 수 있습니다.", ephemeral=True)
            return

        self.parent_view.selected_profile_id = self.values[0]
        selected_prof = db.get_user_profile(self.values[0])
        p_name = selected_prof["profile_name"] if selected_prof else "선택된 프로필"

        # Enable mode buttons
        self.parent_view.solo_btn.disabled = False
        self.parent_view.collab_btn.disabled = False

        await interaction.response.edit_message(
            content=f"🎯 **[프로필 선택 완료]** `{p_name}`\n\n"
                    "아래에서 방송 유형(모드)을 선택해 주시면 가편집이 시작됩니다:",
            view=self.parent_view,
        )


class ProfileAndModeSelectionView(discord.ui.View):
    def __init__(
        self,
        vod_url_or_no: str,
        discord_user_id: int,
        profiles: list[dict[str, Any]],
        video_title: str = "치지직 다시보기",
    ):
        super().__init__(timeout=300)
        self.vod_url_or_no = vod_url_or_no
        self.discord_user_id = discord_user_id
        self.profiles = profiles
        self.video_title = video_title
        self.video_no = extract_chzzk_video_no(vod_url_or_no) or vod_url_or_no
        self.selected_profile_id = profiles[0]["profile_id"] if profiles else ""

        # Step 1: Add profile dropdown
        self.dropdown = ProfileSelectDropdown(profiles, self)
        self.add_item(self.dropdown)

        # Step 2: Buttons
        self.solo_btn = discord.ui.Button(label="🎤 솔로 방송 모드", style=discord.ButtonStyle.primary, custom_id="btn_solo_exec", disabled=False)
        self.collab_btn = discord.ui.Button(label="👥 합방 / 콜라보 모드", style=discord.ButtonStyle.success, custom_id="btn_collab_exec", disabled=False)

        self.solo_btn.callback = self._on_solo_click
        self.collab_btn.callback = self._on_collab_click

        self.add_item(self.solo_btn)
        self.add_item(self.collab_btn)

    async def _on_solo_click(self, interaction: discord.Interaction):
        await self._execute(interaction, "solo", "솔로 방송 모드")

    async def _on_collab_click(self, interaction: discord.Interaction):
        await self._execute(interaction, "collab", "합방 / 콜라보 모드")

    async def _execute(self, interaction: discord.Interaction, mode: str, mode_kr: str):
        if interaction.user.id != self.discord_user_id:
            await interaction.response.send_message("❌ 본인의 요청에서만 실행할 수 있습니다.", ephemeral=True)
            return

        # Quota and Credit Verification Pipeline
        today_str = datetime.date.today().isoformat()
        summary = db.get_user_credit_summary(self.discord_user_id, today_str)

        is_free = False
        if summary["is_vip"] and summary["free_remaining_today"] > 0:
            is_free = True
            db.record_daily_usage(self.discord_user_id, is_free_quota=True, video_no=self.video_no)
        else:
            # Must consume 1 credit
            ok, rem = db.deduct_user_credit(self.discord_user_id, reason=f"가편집 VOD: {self.video_no}")
            if not ok:
                await interaction.response.send_message(
                    f"⚠️ **[크레딧 부족 안내]**\n"
                    f"가편집을 진행하기 위한 크레딧이 부족합니다. (보유 잔액: `{rem}`개)\n"
                    f"• 1일 무료 2회 슬롯을 모두 소진하셨거나 일반 회원 상태입니다.\n"
                    f"• 잔액 확인: `/크레딧`\n"
                    f"• 충전 문의: 관리자에게 문의해 주세요.",
                    ephemeral=True,
                )
                return
            db.record_daily_usage(self.discord_user_id, is_free_quota=False, video_no=self.video_no)

        # Disable view items
        for item in self.children:
            item.disabled = True

        prof = db.get_user_profile(self.selected_profile_id)
        p_name = prof["profile_name"] if prof else "기본 프로필"

        await interaction.response.edit_message(
            content=f"🚀 **[{mode_kr}] 가편집 연산이 시작되었습니다!**\n"
                    f"• 적용 프로필: `{p_name}`\n"
                    f"• 소모 내역: {'🎁 당일 무료 슬롯 (1회)' if is_free else '⚡ 1 크레딧 차감'}\n"
                    f"• 완료 시 이곳으로 XML/SRT 가편집 패키지가 자동 전송됩니다.",
            view=self,
        )

        # Launch background task
        asyncio.create_task(
            execute_vod_pipeline_and_deliver(
                vod_url_or_no=self.vod_url_or_no,
                streamer_name=p_name,
                target_dna_profile=p_name,
                discord_user_id=self.discord_user_id,
                status_channel=interaction.channel,
                selected_mode=mode,
            )
        )


# =============================================================================
# User Slash Commands
# =============================================================================


@bot.tree.command(
    name="프로필등록",
    description="3편의 솔로 영상과 3편의 합방 유튜브 링크를 분석하여 개인 전용 발화 프로필을 생성합니다.",
)
async def cmd_register_profile(interaction: discord.Interaction):
    modal = ProfileRegistrationModal()
    await interaction.response.send_modal(modal)


@bot.tree.command(
    name="내프로필",
    description="본인이 등록한 발화 프로필 목록을 조회하고 관리합니다.",
)
async def cmd_my_profiles(interaction: discord.Interaction):
    profiles = db.get_user_profiles(interaction.user.id)
    if not profiles:
        await interaction.response.send_message(
            "⚠️ 등록된 발화 프로필이 없습니다. 먼저 `/프로필등록` 명령어로 프로필을 생성해 주세요.",
            ephemeral=True,
        )
        return

    lines = ["📋 **[내 등록 발화 프로필 목록]** (오직 본인 계정에만 비공개 격리 보관)"]
    for i, p in enumerate(profiles, start=1):
        s_asl = p.get("solo_profile", {}).get("avg_shot_length", 3.8)
        c_asl = p.get("collab_profile", {}).get("avg_shot_length", 2.2)
        lines.append(f"**{i}. {p['profile_name']}** (ID: `{p['profile_id']}`)\n   • 솔로 ASL: `{s_asl}s` | 합방 ASL: `{c_asl}s`")

    lines.append("\n👉 프로필 삭제를 원하시면 `/프로필삭제 [프로필ID]` 명령어를 이용해 주세요.")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(
    name="프로필삭제",
    description="등록한 특정 발화 프로필을 삭제합니다.",
)
@app_commands.describe(프로필id="삭제할 프로필의 ID (예: prof_abc123)")
async def cmd_delete_profile(interaction: discord.Interaction, 프로필id: str):
    success = db.delete_user_profile(프로필id.strip(), discord_user_id=interaction.user.id)
    if success:
        await interaction.response.send_message(f"✅ 프로필(`{프로필id}`)이 정상적으로 삭제되었습니다.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ 해당 프로필을 찾을 수 없거나 삭제 권한이 없습니다.", ephemeral=True)


@bot.tree.command(
    name="크레딧",
    description="본인의 회원 등급, 오늘 남은 무료 가편집 횟수, 크레딧 잔액을 확인합니다.",
)
async def cmd_my_credits(interaction: discord.Interaction):
    today_str = datetime.date.today().isoformat()
    summary = db.get_user_credit_summary(interaction.user.id, today_str)

    vip_badge = "👑 VIP 스트리머 (1일 2회 무료 제공)" if summary["is_vip"] else "👤 일반 크리에이터"
    free_info = f"• **오늘 남은 무료 가편집:** `{summary['free_remaining_today']} / 2회`" if summary["is_vip"] else "• **일일 무료 혜택:** 일반 회원 (크레딧 전용)"

    msg = f"""💳 **[ChannelDNA 크레딧 및 계정 현황]**

• **회원 등급:** {vip_badge}
{free_info}
• **보유 크레딧 잔액:** `{summary['credits']}개`

ℹ️ **크레딧 이용 안내:** 
영상 길이에 상관없이 **VOD 1개를 가편집할 때마다 1크레딧**이 차감됩니다.

💡 *크레딧 충전이 필요하신 경우 `/크레딧충전` 명령어를 사용해주세요.*"""
    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(
    name="크레딧충전",
    description="가편집 크레딧 요금 안내를 확인하거나 결제 링크를 생성합니다.",
)
@app_commands.describe(
    amount="충전할 수량 (숫자 미입력 시 요금표 안내가 출력됩니다)"
)
async def cmd_charge_credits(interaction: discord.Interaction, amount: int = None):
    if amount is None:
        msg = (
            "💰 **[ChannelDNA 크레딧 요금 안내]**\n\n"
            "저희 봇은 **영상 길이에 상관없이 무조건 VOD 1개당 1크레딧**이 차감됩니다.\n"
            "*(1시간 영상도 1크레딧, 12시간 대규모 합방 영상도 똑같이 1크레딧!)*\n\n"
            "• **결제 단가:** 1크레딧 = 3,000원\n\n"
            "👉 **충전하는 방법:**\n"
            "채팅창에 `/크레딧충전 [수량]`을 적고 엔터를 치시면 즉시 결제 링크가 생성됩니다.\n"
            "*(예시: 10개를 충전하고 싶으시면 `/크레딧충전 10` 입력)*"
        )
        await interaction.response.send_message(msg, ephemeral=True)
        return

    if amount < 1:
        await interaction.response.send_message("❌ 최소 1크레딧 이상 충전해야 합니다.", ephemeral=True)
        return

    price = amount * 3000
    if price < 3000:
        await interaction.response.send_message("❌ 페이앱 결제 최소 금액은 3,000원입니다.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    
    import aiohttp
    import urllib.parse
    
    url = "https://api.payapp.kr/oapi/apiLoad.html"
    payload = {
        "cmd": "payrequest",
        "userid": config.PAYAPP_USERID,
        "linkkey": config.PAYAPP_LINKKEY,
        "goodname": f"채널DNA 가편집 크레딧 {amount}개 충전",
        "price": str(price),
        "recvphone": "01000000000",
        "smsuse": "n",
        "var1": str(interaction.user.id),
        "feedbackurl": "https://roughcut-bot.onrender.com/api/payapp/webhook"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload) as resp:
                text = await resp.text()
                # Parse query string format response
                parsed = dict(urllib.parse.parse_qsl(text))
                
                if parsed.get("state") == "1" and "payurl" in parsed:
                    payurl = parsed["payurl"]
                    msg = (
                        f"💰 **크레딧 충전 결제 링크가 생성되었습니다!**\n\n"
                        f"• **충전 크레딧:** {amount}개 *(처리 가능한 영상 갯수)*\n"
                        f"• **결제 금액:** {price:,}원\n\n"
                        f"ℹ️ **이용 안내:** 방송 길이에 상관없이 VOD 1개당 1크레딧이 차감됩니다.\n"
                        f"👉 [**여기**]({payurl})를 클릭하여 결제를 진행해 주세요.\n"
                        f"*(결제가 완료되면 봇이 자동으로 확인 후 크레딧을 즉시 충전해 드립니다.)*"
                    )
                    await interaction.followup.send(msg)
                else:
                    error_msg = parsed.get("errorMessage", "알 수 없는 오류")
                    await interaction.followup.send(f"❌ **결제 링크 생성에 실패했습니다.**\n사유: {error_msg}")
    except Exception as e:
        await interaction.followup.send(f"❌ **서버 통신 오류가 발생했습니다.**\n{e}")


@bot.tree.command(
    name="가편집",
    description="치지직 VOD 링크를 입력하여 등록된 프로필 및 모드를 선택하고 가편집 XML을 생성합니다.",
)
@app_commands.describe(치지직_링크="치지직 다시보기 영상 링크 (예: https://chzzk.naver.com/video/1049281)")
async def cmd_manual_roughcut(interaction: discord.Interaction, 치지직_링크: str):
    user_id = interaction.user.id
    profiles = db.get_user_profiles(user_id)

    if not profiles:
        await interaction.response.send_message(
            "⚠️ **[스트리머 발화 프로필 미등록 안내]**\n\n"
            "등록된 발화 프로필이 없습니다.\n"
            "임의의 프로필로 가편집을 진행하면 컷팅 품질이 떨어지고 자막 싱크가 어긋날 수 있습니다.\n\n"
            "먼저 아래 명령어로 프로필을 1회 등록해 주세요:\n"
            "👉 `/프로필등록`",
            ephemeral=True,
        )
        return

    v_no = extract_chzzk_video_no(치지직_링크)
    if not v_no:
        await interaction.response.send_message("❌ 올바른 치지직 다시보기 영상 링크를 입력해 주세요.", ephemeral=True)
        return

    meta = fetch_chzzk_video_meta(v_no)
    v_title = meta.get("title") if meta else "치지직 다시보기"
    v_url = f"https://chzzk.naver.com/video/{v_no}"

    view = ProfileAndModeSelectionView(
        vod_url_or_no=v_url,
        discord_user_id=user_id,
        profiles=profiles,
        video_title=v_title,
    )

    notice_text = (
        f"🎬 **[VOD 자동 가편집 요청]**\n"
        f"• **방송 제목:** {v_title}\n"
        f"• **영상 링크:** `{v_url}`\n\n"
        f"적용할 **스트리머 발화 프로필**을 선택한 뒤 **솔로/합방 모드**를 클릭해 주세요:"
    )
    await interaction.response.send_message(notice_text, view=view, ephemeral=False)


@bot.tree.command(
    name="분석",
    description="[별칭] 치지직 다시보기 링크를 입력하여 가편집을 시작합니다.",
)
@app_commands.describe(치지직_링크="치지직 다시보기 영상 링크")
async def cmd_manual_analyze(interaction: discord.Interaction, 치지직_링크: str):
    await cmd_manual_roughcut(interaction, 치지직_링크)






# Active User & Video Task Registry for Cancelling Previous Jobs upon Re-selection
_active_user_tasks: dict[int, asyncio.Task] = {}
_active_video_tasks: dict[str, asyncio.Task] = {}


class ModeSelectionView(discord.ui.View):
    def __init__(
        self,
        vod_url_or_no: str,
        streamer_name: str,
        target_dna_profile: str,
        discord_user_id: int,
    ):
        super().__init__(timeout=None)
        self.vod_url_or_no = vod_url_or_no
        self.streamer_name = streamer_name
        self.target_dna_profile = target_dna_profile
        self.discord_user_id = discord_user_id
        self.video_no = extract_chzzk_video_no(vod_url_or_no) or vod_url_or_no

    @discord.ui.button(
        label="🎙️ 솔로 모드",
        style=discord.ButtonStyle.primary,
        custom_id="btn_solo_mode",
    )
    async def solo_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_selection(interaction, "solo", "솔로 모드")

    @discord.ui.button(
        label="👥 합방 모드",
        style=discord.ButtonStyle.success,
        custom_id="btn_collab_mode",
    )
    async def collab_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_selection(interaction, "collab", "합방 모드")

    async def _handle_selection(self, interaction: discord.Interaction, mode: str, mode_kr: str):
        if interaction.user.id != self.discord_user_id:
            await interaction.response.send_message("❌ 본인의 알림만 선택할 수 있습니다.", ephemeral=True)
            return

        # 1. Cancel previous active task for this user if still running
        if self.discord_user_id in _active_user_tasks:
            prev_user_task = _active_user_tasks[self.discord_user_id]
            if not prev_user_task.done():
                prev_user_task.cancel()
                print(f"[Task Cancelled] Aborted previous task for user {self.discord_user_id} due to new selection.")

        if self.video_no in _active_video_tasks:
            prev_task = _active_video_tasks[self.video_no]
            if not prev_task.done():
                prev_task.cancel()
                print(f"[Task Cancelled] Aborted previous task for video {self.video_no} due to re-selection.")

        # 2. Disable buttons to prevent duplicate clicks
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        await interaction.response.edit_message(
            content=f"✅ **[{mode_kr}]**가 선택되었습니다. 다시보기 가편집 및 AI 자막 생성을 시작합니다.",
            view=self,
        )

        # 3. Launch new pipeline task and track in registry
        task = asyncio.create_task(
            execute_vod_pipeline_and_deliver(
                vod_url_or_no=self.vod_url_or_no,
                streamer_name=self.streamer_name,
                target_dna_profile=self.target_dna_profile,
                discord_user_id=self.discord_user_id,
                status_channel=interaction.channel,
                selected_mode=mode,
            )
        )
        _active_user_tasks[self.discord_user_id] = task
        _active_video_tasks[self.video_no] = task


# =============================================================================
# Core Pipeline Execution & DM Delivery Helper
# =============================================================================


async def execute_vod_pipeline_and_deliver(
    vod_url_or_no: str,
    streamer_name: str,
    target_dna_profile: str,
    discord_user_id: int,
    status_channel: discord.abc.Messageable | None = None,
    selected_mode: str = "solo",
) -> bool:
    """Executes the Two-Track Modal GPU pipeline and delivers the files to the user's DM."""
    target_dna = (target_dna_profile or streamer_name).strip()
    solo_p = db.get_profile(f"{target_dna}_Solo") or db.get_profile(target_dna)
    collab_p = db.get_profile(f"{target_dna}_Collab")
    solo_dict = solo_p.to_dict() if solo_p else None
    collab_dict = collab_p.to_dict() if collab_p else None

    print(f"[Pipeline Start] {streamer_name} ({vod_url_or_no}) -> DNA: {target_dna}")

    status_msg = None
    stop_heartbeat = asyncio.Event()

    async def _typing_heartbeat():
        while not stop_heartbeat.is_set():
            try:
                if status_channel:
                    async with status_channel.typing():
                        await asyncio.sleep(8)
                else:
                    await asyncio.sleep(8)
            except Exception:
                await asyncio.sleep(8)

    mode_kr = "솔로 모드" if selected_mode == "solo" else ("합방 모드" if selected_mode == "collab" else "전체 모드")

    if status_channel:
        try:
            status_msg = await status_channel.send(
                f"⏳ **[{mode_kr}] 다시보기 분석을 시작합니다.**\n"
                "• 방송 분량에 따라 수 분 소요될 수 있으며, 완료되면 이곳으로 가편집 패키지를 보내드립니다.\n"
                "• ⚙️ *진행 상태: 음성 수집 및 AI 하이라이트 연산 중...*"
            )
        except Exception:
            pass

    heartbeat_task = asyncio.create_task(_typing_heartbeat())

    # Run Pipeline (Modal Cloud or Local Fallback)
    try:
        if config.USE_MODAL_CLOUD:
            try:
                import modal
                remote_fn = modal.Function.from_name(
                    "channel-dna-cloud", "process_chzzk_vod_cloud"
                )
                result = await asyncio.to_thread(
                    remote_fn.remote,
                    vod_url_or_no,
                    streamer_name,
                    solo_dict,
                    collab_dict,
                    selected_mode,
                )
            except Exception as cloud_err:
                print(f"[Modal Cloud Failed, fallback to local] {cloud_err}")
                from modal_app import process_chzzk_vod_local
                result = await asyncio.to_thread(
                    process_chzzk_vod_local,
                    vod_url_or_no,
                    streamer_name,
                    solo_dict,
                    collab_dict,
                    selected_mode,
                )
        else:
            from modal_app import process_chzzk_vod_local
            result = await asyncio.to_thread(
                process_chzzk_vod_local,
                vod_url_or_no,
                streamer_name,
                solo_dict,
                collab_dict,
                selected_mode,
            )
    finally:
        stop_heartbeat.set()
        heartbeat_task.cancel()

    if not result or not result.get("success"):
        print(f"[Pipeline Execution Failed for {vod_url_or_no}]")
        if status_msg:
            try:
                await status_msg.edit(content="❌ **다시보기 분석 중 오류가 발생했습니다.** 다시 시도해 주세요.")
            except Exception:
                pass
        return False

    if status_msg:
        try:
            await status_msg.edit(
                content=f"✅ **[{mode_kr}] 분석 및 AI 자막 생성이 완료되었습니다!**\n"
                        "• 아래 파일을 확인해 주세요."
            )
        except Exception:
            pass

    b_title = result.get("broadcast_title", "치지직 다시보기")
    b_date = result.get("broadcast_date", "20260825")
    rec_filename = result.get("recommended_filename", f"{b_date}_{b_title}.mp4")

    solo_xml = result.get("solo_xml_content", "")
    collab_xml = result.get("collab_xml_content", "")
    srt_content = result.get("srt_content", "")
    guide_txt = result.get("guide_txt_content", "")

    files_to_send = []
    file_desc_lines = []

    if solo_xml:
        files_to_send.append(
            discord.File(
                io.BytesIO(solo_xml.encode("utf-8")),
                filename=f"{b_date}_{streamer_name}_Solo_60fps.xml",
            )
        )
        file_desc_lines.append("• Solo (XML): 개인 방송 기준 가편집 타임라인 파일")

    if collab_xml:
        files_to_send.append(
            discord.File(
                io.BytesIO(collab_xml.encode("utf-8")),
                filename=f"{b_date}_{streamer_name}_Collab_60fps.xml",
            )
        )
        file_desc_lines.append("• Collab (XML): 합방 및 다인 방송 기준 가편집 타임라인 파일")

    if srt_content:
        files_to_send.append(
            discord.File(
                io.BytesIO(srt_content.encode("utf-8")),
                filename=f"{b_date}_{streamer_name}_자막.srt",
            )
        )
        file_desc_lines.append("• 자막 (SRT): 한국어 특화 고정밀 초벌 자막 파일")

    marker_count = (
        result.get("solo_marker_count", 0)
        if selected_mode == "solo"
        else (
            result.get("collab_marker_count", 0)
            if selected_mode == "collab"
            else (result.get("solo_marker_count", 0) + result.get("collab_marker_count", 0))
        )
    )

    desc_block = "\n".join(file_desc_lines)
    delivery_msg = f"""[가편집 파일 전송 안내 - {mode_kr}]

• 방송 제목: {b_title}
• 방송 일시: {b_date}
• 추출 컷: {marker_count}개 하이라이트 구간

[1. 원본 영상 파일명 설정]
편집 프로그램에서 타임라인을 자동 연결하기 위해, 원본 영상(mp4)의 이름을 아래와 동일하게 설정해 주세요.
👉 {rec_filename}

[2. 첨부 파일 구성]
{desc_block}

[3. 편집 프로그램 적용 방법]
1. 원본 영상(mp4)의 파일명을 위의 권장 파일명과 동일하게 변경합니다.
2. 원본 영상과 첨부 파일(XML, SRT)을 동일한 폴더에 함께 둡니다.
3. 편집기(프리미어 / 파이널컷 / 다빈치)에서 [파일] ➔ [가져오기(Import)]로 XML 파일을 불러옵니다.
4. 생성된 가편집 타임라인 위에 SRT 자막 파일을 드래그하여 배치합니다.
"""

    await outbound_queue.put(OutboundMessage(
        user_id=discord_user_id,
        content=delivery_msg,
        files=files_to_send
    ))
    print(f"[OK] Queued package delivery to Discord User: {discord_user_id}")
    return True
# =============================================================================
# DM Message Listener (Link Auto-Detection with Deduplication)
# =============================================================================

_processed_message_ids: set[int] = set()


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Deduplicate repeated Gateway events for the same message ID
    if message.id in _processed_message_ids:
        return
    _processed_message_ids.add(message.id)
    if len(_processed_message_ids) > 1000:
        _processed_message_ids.clear()

    # Process Commands first
    await bot.process_commands(message)

    # Detect VOD link sent directly in 1:1 DM
    if isinstance(message.channel, discord.DMChannel):
        clean_content = message.content.strip()
        if "chzzk.naver.com/video/" in clean_content or (
            clean_content.isdigit() and len(clean_content) >= 5
        ):
            user_id = message.author.id
            profiles = db.get_user_profiles(user_id)
            if not profiles:
                await message.channel.send(
                    "⚠️ **[스트리머 발화 프로필 미등록 안내]**\n"
                    "등록된 발화 프로필이 없습니다. 먼저 `/프로필등록` 명령어로 3+3 영상을 등록해 주세요."
                )
                return

            v_no = extract_chzzk_video_no(clean_content)
            if not v_no:
                await message.channel.send("❌ 올바른 치지직 다시보기 영상 링크를 입력해 주세요.")
                return

            meta = fetch_chzzk_video_meta(v_no)
            v_title = meta.get("title") if meta else "치지직 다시보기"
            v_url = f"https://chzzk.naver.com/video/{v_no}"

            view = ProfileAndModeSelectionView(
                vod_url_or_no=v_url,
                discord_user_id=user_id,
                profiles=profiles,
                video_title=v_title,
            )
            notice_text = (
                f"🎬 **[다시보기 분석 요청 접수]**\n"
                f"• **방송 제목:** {v_title}\n"
                f"• **영상 링크:** `{v_url}`\n\n"
                "적용할 **발화 프로필**을 선택한 후 **솔로/합방 모드**를 클릭해 주세요:"
            )
            await message.channel.send(content=notice_text, view=view)


# =============================================================================
# 24/7 Chzzk VOD Watcher Background Loop (Every 2 Minutes)
# =============================================================================


@tasks.loop(seconds=config.CHZZK_POLL_INTERVAL_SEC)
async def chzzk_watcher_loop():
    active_bindings = db.get_active_streamer_bindings()
    if not active_bindings:
        return

    for item in active_bindings:
        ch_id = item["channel_id"]
        st_name = item["streamer_name"]
        target_dna = item.get("target_dna_profile") or st_name
        discord_user_id = item["master_discord_id"]
        last_v_no = item.get("last_processed_video_no") or ""

        try:
            vods = fetch_chzzk_vod_list(ch_id, page_size=1)
            if not vods:
                continue

            latest_vod = vods[0]
            v_no = str(latest_vod.get("video_no") or "")
            v_title = latest_vod.get("title") or "치지직 다시보기"
            v_duration = latest_vod.get("duration", 0)
            v_url = latest_vod.get("vod_url") or f"https://chzzk.naver.com/video/{v_no}"

            # Filter 1: Check if new VOD
            if not v_no or v_no == last_v_no:
                continue

            # Filter 2: Check minimum duration (exclude short tests under 20 mins)
            if v_duration < config.MIN_VOD_DURATION_SEC:
                db.update_last_processed_video_no(ch_id, v_no)
                continue

            print(f"[New VOD Detected] {st_name} - {v_title} ({v_duration}s).")

            user = await bot.fetch_user(discord_user_id)
            if user:
                view = ModeSelectionView(
                    vod_url_or_no=v_url,
                    streamer_name=st_name,
                    target_dna_profile=target_dna,
                    discord_user_id=discord_user_id,
                )
                notice_text = (
                    f"[생방송 종료 감지 알림]\n"
                    f"방송 제목: {v_title}\n"
                    f"영상 링크: `{v_url}`\n\n"
                    "가편집을 진행하시려면 아래 편집 모드 버튼을 선택해 주시기 바랍니다.\n"
                    "• 솔로 모드: 개인 방송 텐션 및 호흡 기준 가편집\n"
                    "• 합방 모드: 디스코드 및 다인 방송 텐션 기준 가편집\n\n"
                    "※ 버튼을 선택하지 않으시면 분석이 진행되지 않습니다."
                )
                await user.send(content=notice_text, view=view)
                db.update_last_processed_video_no(ch_id, v_no)

        except Exception as err:
            print(f"[Watcher Error for channel {ch_id}] {err}")


@chzzk_watcher_loop.before_loop
async def before_watcher_loop():
    await bot.wait_until_ready()


async def main():
    try:
        await start_health_server()
    except Exception as e:
        print(f"[Health Server Startup Warning] {e}", flush=True)
    
    token = os.environ.get("DISCORD_BOT_TOKEN") or config.BOT_TOKEN
    print(f"[Bot] Attempting to connect Discord bot with token prefix: {token[:10]}...", flush=True)
    await bot.start(token)


def run_discord_bot():
    """Entry point for running the Discord bot."""
    import traceback
    acquire_singleton_lock()
    token = os.environ.get("DISCORD_BOT_TOKEN") or config.BOT_TOKEN
    if not token or token == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("⚠ DISCORD_BOT_TOKEN is not set in environment or config.", flush=True)
        return
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Bot] Stopped by keyboard interrupt.", flush=True)
    except Exception as err:
        print(f"[CRITICAL BOT CRASH] {err}", flush=True)
        traceback.print_exc()
        raise


if __name__ == "__main__":
    run_discord_bot()
