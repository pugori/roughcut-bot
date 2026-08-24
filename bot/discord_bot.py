"""ChannelDNA 24/7 Chzzk Monitoring & Automatic Rough Cut Delivery Discord Bot."""

import asyncio
import io
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

# Singleton Process Lock Helper
_lock_socket = None


def acquire_singleton_lock() -> bool:
    global _lock_socket
    _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _lock_socket.bind(("127.0.0.1", 49151))
        return True
    except socket.error:
        print("[FATAL] Another instance of RoughCut Discord Bot is already running. Exiting.")
        sys.exit(0)

import discord
from discord import app_commands
from discord.ext import commands, tasks

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


async def handle_health(request):
    return web.Response(text="RoughCut Discord Bot 24/7 is Live!")


async def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[OK] Health check server listening on port {port}")


# =============================================================================
# Bot Lifecycle Events
# =============================================================================


@bot.event
async def on_ready():
    print(f"[OK] RoughCut Discord Bot logged in as: {bot.user} (ID: {bot.user.id})")
    try:
        await start_health_server()
    except Exception as e:
        print(f"[Health Server Warning] {e}")

    try:
        synced = await bot.tree.sync()
        print(f"[OK] Synced {len(synced)} slash commands globally.")
    except Exception as e:
        print(f"[WARN] Slash command sync warning: {e}")

    if not chzzk_watcher_loop.is_running():
        chzzk_watcher_loop.start()
        print("[OK] 24/7 Chzzk VOD Watcher loop started.")


# =============================================================================
# Admin Slash Commands (Restricted to ADMIN_USER_ID)
# =============================================================================


@bot.tree.command(
    name="암호발급",
    description="[관리자] 스트리머용 1회용 인증 암호를 발급하고 모니터링 대기열에 등록합니다.",
)
@app_commands.describe(
    스트리머명="등록할 스트리머 이름 (예: 양망두)",
    치지직주소="치지직 채널 링크 또는 32자리 채널 ID",
    적용dna="적용할 DNA 스타일 이름 (비워두면 본인 스타일 적용)",
)
async def cmd_issue_passcode(
    interaction: discord.Interaction,
    스트리머명: str,
    치지직주소: str,
    적용dna: str = "",
):
    # Admin Permission Check
    if config.ADMIN_USER_ID != 0 and interaction.user.id != config.ADMIN_USER_ID:
        await interaction.response.send_message(
            "❌ 관리자만 실행할 수 있는 명령어입니다.", ephemeral=True
        )
        return

    ch_id = extract_chzzk_channel_id(치지직주소)
    if not ch_id or len(ch_id) < 10:
        await interaction.response.send_message(
            "❌ 올바른 치지직 채널 주소 또는 32자리 채널 ID를 입력해 주세요.",
            ephemeral=True,
        )
        return

    dna_prof = 적용dna.strip() if 적용dna else 스트리머명.strip()
    passcode = generate_secure_passcode(스트리머명)
    db.create_passcode_binding(
        channel_id=ch_id,
        streamer_name=스트리머명,
        passcode=passcode,
        target_dna_profile=dna_prof,
    )

    card_text = f"""[1회용 암호 발급 완료]

- 스트리머: {스트리머명}
- 적용 DNA: {dna_prof} 스타일
- 채널 ID: {ch_id}
- 인증 암호: `{passcode}`

[전달용 안내문]
```text
안녕하세요. 치지직 방송 종료 시 가편집 타임라인과 자막을 자동 전송하는 봇입니다.

1. 봇 초대 링크를 통해 봇과의 1:1 대화방을 엽니다.
2. 대화창에 아래 명령어를 입력하여 등록을 완료해 주세요.
👉 /인증 암호:{passcode}
```
"""
    await interaction.response.send_message(card_text, ephemeral=True)


@bot.tree.command(
    name="현황",
    description="[관리자] 현재 등록된 스트리머 모니터링 및 인증 바인딩 현황을 조회합니다.",
)
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





# =============================================================================
# Core Pipeline Execution & DM Delivery Helper
# =============================================================================


async def execute_vod_pipeline_and_deliver(
    vod_url_or_no: str,
    streamer_name: str,
    target_dna_profile: str,
    discord_user_id: int,
    status_channel: discord.abc.Messageable | None = None,
) -> bool:
    """Executes the Two-Track Modal GPU pipeline and delivers the 4 files to the user's DM."""
    target_dna = (target_dna_profile or streamer_name).strip()
    solo_p = db.get_profile(f"{target_dna}_Solo") or db.get_profile(target_dna)
    collab_p = db.get_profile(f"{target_dna}_Collab")
    solo_dict = solo_p.to_dict() if solo_p else None
    collab_dict = collab_p.to_dict() if collab_p else None

    print(f"[Pipeline Start] {streamer_name} ({vod_url_or_no}) -> DNA: {target_dna}")

    if status_channel:
        try:
            await status_channel.send("⏳ 요청하신 다시보기 분석을 시작합니다. (약 2~3분 소요)")
        except Exception:
            pass

    # Run Pipeline (Modal Cloud or Local Fallback)
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
            )
    else:
        from modal_app import process_chzzk_vod_local
        result = await asyncio.to_thread(
            process_chzzk_vod_local,
            vod_url_or_no,
            streamer_name,
            solo_dict,
            collab_dict,
        )

    if not result or not result.get("success"):
        print(f"[Pipeline Execution Failed for {vod_url_or_no}]")
        if status_channel:
            try:
                await status_channel.send("❌ 다시보기 분석 중 오류가 발생했습니다. 다시 시도해 주세요.")
            except Exception:
                pass
        return False

    b_title = result.get("broadcast_title", "치지직 다시보기")
    b_date = result.get("broadcast_date", "20260825")
    rec_filename = result.get("recommended_filename", f"{b_date}_{b_title}.mp4")

    solo_xml = result.get("solo_xml_content", "")
    collab_xml = result.get("collab_xml_content", "")
    srt_content = result.get("srt_content", "")
    guide_txt = result.get("guide_txt_content", "")

    files_to_send = []
    if solo_xml:
        files_to_send.append(
            discord.File(
                io.BytesIO(solo_xml.encode("utf-8")),
                filename=f"{b_date}_{streamer_name}_Solo_60fps.xml",
            )
        )
    if collab_xml:
        files_to_send.append(
            discord.File(
                io.BytesIO(collab_xml.encode("utf-8")),
                filename=f"{b_date}_{streamer_name}_Collab_60fps.xml",
            )
        )
    if srt_content:
        files_to_send.append(
            discord.File(
                io.BytesIO(srt_content.encode("utf-8")),
                filename=f"{b_date}_{streamer_name}_자막.srt",
            )
        )
    if guide_txt:
        files_to_send.append(
            discord.File(
                io.BytesIO(guide_txt.encode("utf-8")),
                filename="가이드.txt",
            )
        )

    delivery_msg = f"""[가편집 파일 전송 안내]

• 방송 제목: {b_title}
• 방송 일시: {b_date}

[1. 원본 영상 파일명 설정]
편집 프로그램에서 파일을 정상적으로 연결하기 위해, 원본 영상(mp4)의 이름을 아래와 동일하게 설정해 주세요.
👉 {rec_filename}

[2. 첨부 파일 구성]
• Solo (XML): 개인 방송 기준 가편집 타임라인 파일
• Collab (XML): 합방 및 다인 방송 기준 가편집 타임라인 파일
• 자막 (SRT): 음성 인식 기반 초벌 자막 파일
• 가이드 (TXT): 편집기 불러오기 및 타임라인 연결 가이드
"""

    user = await bot.fetch_user(discord_user_id)
    if user:
        await user.send(content=delivery_msg, files=files_to_send)
        print(f"[OK] Successfully delivered package to Discord User: {discord_user_id}")
        return True
    return False


# =============================================================================
# Streamer / Client Slash Commands
# =============================================================================


@bot.tree.command(
    name="인증",
    description="전달받은 1회용 암호로 채널 등록을 완료합니다.",
)
@app_commands.describe(암호="전달받은 1회용 인증 암호 (예: YMDU-8492)")
async def cmd_verify_passcode(interaction: discord.Interaction, 암호: str):
    user_id = interaction.user.id
    welcome_notice = """[등록 완료 안내]

치지직 채널 등록이 정상적으로 완료되었습니다.

[서비스 이용 안내]
• 자동 생성: 치지직 방송 종료 시 가편집 타임라인 및 자막 자동 전달
• 수동 분석: 지난 방송 링크(URL)를 이 대화창에 입력 시 즉시 생성

[제공 파일 안내]
• Solo (XML): 개인 방송 기준 가편집 타임라인 파일
• Collab (XML): 합방 및 다인 방송 기준 가편집 타임라인 파일
• 자막 (SRT): 음성 인식 기반 초벌 자막 파일
• 가이드 (TXT): 편집기 불러오기 및 타임라인 연결 가이드
"""

    # Check if already bound
    existing = db.get_binding_by_discord_user_id(user_id)
    if existing:
        await interaction.response.send_message(welcome_notice, ephemeral=False)
        return

    res = db.verify_and_bind_passcode(passcode=암호, discord_user_id=user_id)
    if not res:
        await interaction.response.send_message(
            "❌ 유효하지 않거나 이미 사용된 암호입니다. 관리자에게 확인해 주세요.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(welcome_notice, ephemeral=False)


@bot.tree.command(
    name="분석",
    description="치지직 다시보기 링크를 수동으로 입력하여 가편집 파일과 자막을 즉시 생성합니다.",
)
@app_commands.describe(다시보기링크="치지직 다시보기 링크 또는 영상 번호 (예: https://chzzk.naver.com/video/1049281)")
async def cmd_manual_analyze(interaction: discord.Interaction, 다시보기링크: str):
    user_id = interaction.user.id
    binding = db.get_binding_by_discord_user_id(user_id)

    if not binding:
        await interaction.response.send_message(
            "❌ 등록된 채널이 없습니다. 먼저 `/인증 [암호]` 명령어로 등록을 완료해 주세요.",
            ephemeral=True,
        )
        return

    # 1. Video ownership verification
    v_no = extract_chzzk_video_no(다시보기링크)
    if not v_no:
        await interaction.response.send_message(
            "❌ 올바른 치지직 다시보기 영상 링크 또는 번호를 입력해 주세요.",
            ephemeral=True,
        )
        return

    meta = fetch_chzzk_video_meta(v_no)
    if not meta:
        await interaction.response.send_message(
            "❌ 해당 치지직 다시보기 영상 정보를 불러올 수 없습니다. 링크를 확인해 주세요.",
            ephemeral=True,
        )
        return

    video_ch_id = meta.get("channel_id", "")
    bound_ch_id = binding.get("channel_id", "")

    if video_ch_id and bound_ch_id and video_ch_id != bound_ch_id:
        req_owner = meta.get("channel_name") or "타 채널"
        await interaction.response.send_message(
            f"❌ 등록된 본인의 치지직 채널 영상만 분석할 수 있습니다.\n"
            f"• 등록 채널: {binding.get('streamer_name')} (`{bound_ch_id[:8]}...`)\n"
            f"• 요청 영상 소유자: {req_owner}",
            ephemeral=True,
        )
        return

    st_name = binding["streamer_name"]
    target_dna = binding.get("target_dna_profile") or st_name

    await interaction.response.send_message(
        "⏳ 요청하신 다시보기 분석을 시작합니다. (약 2~3분 소요)",
        ephemeral=False,
    )

    asyncio.create_task(
        execute_vod_pipeline_and_deliver(
            vod_url_or_no=다시보기링크.strip(),
            streamer_name=st_name,
            target_dna_profile=target_dna,
            discord_user_id=user_id,
            status_channel=None,
        )
    )


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
            binding = db.get_binding_by_discord_user_id(user_id)
            if not binding:
                await message.channel.send(
                    "❌ 등록된 채널이 없습니다. 먼저 `/인증 [암호]` 명령어로 채널을 등록해 주세요."
                )
                return

            # Video ownership verification
            v_no = extract_chzzk_video_no(clean_content)
            if not v_no:
                await message.channel.send("❌ 올바른 치지직 다시보기 영상 링크를 입력해 주세요.")
                return

            meta = fetch_chzzk_video_meta(v_no)
            if not meta:
                await message.channel.send("❌ 해당 치지직 다시보기 영상 정보를 불러올 수 없습니다.")
                return

            video_ch_id = meta.get("channel_id", "")
            bound_ch_id = binding.get("channel_id", "")

            if video_ch_id and bound_ch_id and video_ch_id != bound_ch_id:
                req_owner = meta.get("channel_name") or "타 채널"
                await message.channel.send(
                    f"❌ 등록된 본인의 치지직 채널 영상만 분석할 수 있습니다.\n"
                    f"• 등록 채널: {binding.get('streamer_name')} (`{bound_ch_id[:8]}...`)\n"
                    f"• 요청 영상 소유자: {req_owner}"
                )
                return

            st_name = binding["streamer_name"]
            target_dna = binding.get("target_dna_profile") or st_name

            asyncio.create_task(
                execute_vod_pipeline_and_deliver(
                    vod_url_or_no=clean_content,
                    streamer_name=st_name,
                    target_dna_profile=target_dna,
                    discord_user_id=user_id,
                    status_channel=message.channel,
                )
            )


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

            success = await execute_vod_pipeline_and_deliver(
                vod_url_or_no=v_url,
                streamer_name=st_name,
                target_dna_profile=target_dna,
                discord_user_id=discord_user_id,
            )

            if success:
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
        print(f"[Health Server Startup Warning] {e}")
    await bot.start(config.BOT_TOKEN)


def run_discord_bot():
    """Entry point for running the Discord bot."""
    acquire_singleton_lock()
    if not config.BOT_TOKEN or config.BOT_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("⚠ DISCORD_BOT_TOKEN is not set in bot/config.py or environment.")
        return
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_discord_bot()
