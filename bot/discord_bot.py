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


# =============================================================================
# Admin Slash Commands (Local GUI is primary, Status/Unbind only)
# =============================================================================


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





# Active Video Task Registry for Cancelling Previous Jobs upon Re-selection
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

        # 1. Cancel previous active task for this video if still running
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

    user = await bot.fetch_user(discord_user_id)
    if user:
        await user.send(content=delivery_msg, files=files_to_send)
        print(f"[OK] Successfully delivered package to Discord User: {discord_user_id}")
        return True
    return False


# =============================================================================
# Streamer / Client Slash Commands
# =============================================================================


# Daily Rate Limiting Tracker (Max 5 requests per user per day)
import datetime
_daily_user_requests: dict[tuple[int, str], int] = {}


def _check_and_increment_daily_rate_limit(user_id: int, max_limit: int = 5) -> bool:
    """Checks and increments user's daily request count. Returns False if limit exceeded."""
    today_str = datetime.date.today().isoformat()
    key = (user_id, today_str)
    current_count = _daily_user_requests.get(key, 0)
    if current_count >= max_limit:
        return False
    _daily_user_requests[key] = current_count + 1
    return True


@bot.tree.command(
    name="인증",
    description="전달받은 1회용 암호로 채널 등록을 완료합니다.",
)
@app_commands.describe(암호="전달받은 1회용 인증 암호 (예: YMDU-8492)")
async def cmd_verify_passcode(interaction: discord.Interaction, 암호: str):
    user_id = interaction.user.id
    welcome_notice = """[서비스 등록 완료]

계정 인증이 정상적으로 완료되었습니다.

[이용 방법]
- 자동 알림: 생방송 종료 시 방종을 자동 감지하여 본 대화창으로 가편집 시작 안내가 전송됩니다.
- 수동 분석: 지난 방송의 경우 치지직 다시보기 링크(URL)를 본 대화창에 전송하면 즉시 분석됩니다.
- 모드 선택: 솔로 모드 / 합방 모드 중 원하는 편집 스타일을 선택합니다.
- 결과 수령: 작업 완료 시 결과물 패키지가 본 대화창으로 자동 전송됩니다.

[제공 파일]
- Final Cut Pro / Premiere Pro 가편집 타임라인 (XML)
- 가편집 타임라인 동기화 자막 (SRT)

[안내 사항]
- 등록된 채널의 영상에 한해 분석이 지원됩니다.
- 입력된 방송 데이터는 작업 완료 즉시 안전하게 파기됩니다.
"""

    # Check if already bound
    existing = db.get_binding_by_discord_user_id(user_id)
    if existing:
        await interaction.response.send_message(welcome_notice, ephemeral=False)
        return

    res = db.verify_and_bind_passcode(passcode=암호, discord_user_id=user_id)
    if not res:
        await interaction.response.send_message(
            "[인증 실패]\n유효하지 않거나 이미 사용된 인증 암호입니다. 관리자에게 확인해 주시기 바랍니다.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(welcome_notice, ephemeral=False)


@bot.tree.command(
    name="분석",
    description="치지직 다시보기 링크를 수동으로 입력하여 가편집 파일과 자막을 즉시 생성합니다.",
)
@app_commands.describe(다시보기링크="치지직 다시보기 링크 (예: https://chzzk.naver.com/video/1049281)")
async def cmd_manual_analyze(interaction: discord.Interaction, 다시보기링크: str):
    user_id = interaction.user.id
    binding = db.get_binding_by_discord_user_id(user_id)

    if not binding:
        await interaction.response.send_message(
            "[접근 권한 제한]\n사전 등록된 계정 전용 서비스입니다. 관리자에게 1회용 인증 암호를 발급받은 후 '/인증 [암호]' 명령어를 진행해 주시기 바랍니다.",
            ephemeral=True,
        )
        return

    # Rate Limiting check
    if not _check_and_increment_daily_rate_limit(user_id, max_limit=5):
        await interaction.response.send_message(
            "[일일 요청 한도 초과]\n금일 요청 가능한 분석 횟수(최대 5회)를 초과하였습니다. 익일 다시 이용해 주시기 바랍니다.",
            ephemeral=True,
        )
        return

    # 1. Video ownership verification
    v_no = extract_chzzk_video_no(다시보기링크)
    if not v_no:
        await interaction.response.send_message(
            "[입력 오류]\n올바른 치지직 다시보기 영상 링크(URL)를 입력해 주시기 바랍니다.",
            ephemeral=True,
        )
        return

    meta = fetch_chzzk_video_meta(v_no)
    if not meta:
        await interaction.response.send_message(
            "[분석 대상 오류]\n해당 치지직 다시보기 영상 정보를 불러올 수 없습니다. 링크를 확인해 주세요.",
            ephemeral=True,
        )
        return

    video_ch_id = meta.get("channel_id", "")
    bound_ch_id = binding.get("channel_id", "")

    if video_ch_id and bound_ch_id and video_ch_id != bound_ch_id:
        await interaction.response.send_message(
            "[분석 대상 오류]\n등록된 채널의 다시보기 영상만 분석 가능합니다. 영상 링크를 다시 확인해 주시기 바랍니다.",
            ephemeral=True,
        )
        return

    st_name = binding["streamer_name"]
    target_dna = binding.get("target_dna_profile") or st_name

    v_url = f"https://chzzk.naver.com/video/{v_no}" if v_no else 다시보기링크.strip()
    view = ModeSelectionView(
        vod_url_or_no=v_url,
        streamer_name=st_name,
        target_dna_profile=target_dna,
        discord_user_id=user_id,
    )
    notice_text = (
        f"[다시보기 분석 요청 접수]\n"
        f"영상 링크: `{v_url}`\n\n"
        "진행할 가편집 스타일을 선택해 주시기 바랍니다.\n"
        "• 솔로 모드: 개인 방송 텐션 및 호흡 기준 가편집\n"
        "• 합방 모드: 디스코드 및 다인 방송 텐션 기준 가편집"
    )
    await interaction.response.send_message(notice_text, view=view, ephemeral=False)


@bot.tree.command(
    name="초기화",
    description="봇이 보낸 이전 안내 및 가편집 메시지들을 일괄 삭제하여 대화창을 청소합니다.",
)
@app_commands.describe(개수="삭제할 최근 메시지 개수 (기본값: 30개, 최대 100개)")
async def cmd_clear_messages(interaction: discord.Interaction, 개수: int = 30):
    await interaction.response.defer(ephemeral=True)
    deleted_count = 0
    channel = interaction.channel
    limit_val = max(1, min(100, 개수))

    if isinstance(channel, discord.DMChannel):
        async for msg in channel.history(limit=limit_val):
            if msg.author.id == bot.user.id:
                try:
                    await msg.delete()
                    deleted_count += 1
                    await asyncio.sleep(0.2)
                except Exception:
                    pass
    else:
        try:
            async for msg in channel.history(limit=limit_val):
                if msg.author.id == bot.user.id:
                    try:
                        await msg.delete()
                        deleted_count += 1
                        await asyncio.sleep(0.2)
                    except Exception:
                        pass
        except Exception:
            pass

    await interaction.followup.send(
        f"대화창 정리 완료: 이전 메시지 {deleted_count}개가 삭제되었습니다.",
        ephemeral=True,
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
                    "[접근 권한 제한]\n사전 등록된 계정 전용 서비스입니다. 관리자에게 1회용 인증 암호를 발급받은 후 '/인증 [암호]' 명령어를 진행해 주시기 바랍니다."
                )
                return

            # Rate Limiting check
            if not _check_and_increment_daily_rate_limit(user_id, max_limit=5):
                await message.channel.send(
                    "[일일 요청 한도 초과]\n금일 요청 가능한 분석 횟수(최대 5회)를 초과하였습니다. 익일 다시 이용해 주시기 바랍니다."
                )
                return

            # Video ownership verification
            v_no = extract_chzzk_video_no(clean_content)
            if not v_no:
                await message.channel.send("[입력 오류]\n올바른 치지직 다시보기 영상 링크를 입력해 주시기 바랍니다.")
                return

            meta = fetch_chzzk_video_meta(v_no)
            if not meta:
                await message.channel.send("[분석 대상 오류]\n해당 치지직 다시보기 영상 정보를 불러올 수 없습니다.")
                return

            video_ch_id = meta.get("channel_id", "")
            bound_ch_id = binding.get("channel_id", "")

            if video_ch_id and bound_ch_id and video_ch_id != bound_ch_id:
                await message.channel.send(
                    "[분석 대상 오류]\n등록된 채널의 다시보기 영상만 분석 가능합니다. 영상 링크를 다시 확인해 주시기 바랍니다."
                )
                return

            st_name = binding["streamer_name"]
            target_dna = binding.get("target_dna_profile") or st_name

            v_url = f"https://chzzk.naver.com/video/{v_no}"
            view = ModeSelectionView(
                vod_url_or_no=v_url,
                streamer_name=st_name,
                target_dna_profile=target_dna,
                discord_user_id=user_id,
            )
            notice_text = (
                f"[다시보기 분석 요청 접수]\n"
                f"영상 링크: `{v_url}`\n\n"
                "진행할 가편집 스타일을 선택해 주시기 바랍니다.\n"
                "• 솔로 모드: 개인 방송 텐션 및 호흡 기준 가편집\n"
                "• 합방 모드: 디스코드 및 다인 방송 텐션 기준 가편집"
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
