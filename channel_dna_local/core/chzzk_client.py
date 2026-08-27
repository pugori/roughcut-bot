"""Chzzk (NAVER) VOD metadata & direct stream client with Anti-Ban stealth."""

from channel_dna_local.core.logger import get_logger

_logger = get_logger(__name__)

import json
import random
import re
import time
import urllib.request
from typing import Any

from channel_dna_local.core.utils import STEALTH_USER_AGENTS


def extract_chzzk_channel_id(channel_input: str) -> str:
    """Extract 32-character Chzzk channel ID from URL, video URL, or raw ID string."""
    clean = channel_input.strip().strip("\"'")
    match = re.search(r"chzzk\.naver\.com/(?:live/|video/)?([a-zA-Z0-9]{32})", clean)
    if match:
        return match.group(1)

    match_hex = re.search(r"([a-zA-Z0-9]{32})", clean)
    if match_hex:
        return match_hex.group(1)

    # If it's a numeric video URL or video_no, resolve channel ID from video metadata
    v_no = extract_chzzk_video_no(clean)
    if v_no:
        try:
            url = f"https://api.chzzk.naver.com/service/v2/videos/{v_no}"
            ua = random.choice(STEALTH_USER_AGENTS)
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                ch_id = data.get("content", {}).get("channel", {}).get("channelId")
                if ch_id:
                    return ch_id
        except Exception as e:
            _logger.debug("Silenced exception: %s", e)

    return clean


def extract_chzzk_video_no(video_input: str) -> str | None:
    """Extract numeric video_no from Chzzk video URL or raw string."""
    clean = video_input.strip().strip("\"'")
    match = re.search(r"chzzk\.naver\.com/video/(\d+)", clean)
    if match:
        return match.group(1)
    if clean.isdigit():
        return clean
    return None


def fetch_chzzk_vod_list(
    channel_input: str, page_size: int = 40
) -> list[dict[str, Any]]:
    """Fetch latest VODs of a Chzzk channel with Anti-Ban stealth emulation."""
    channel_id = extract_chzzk_channel_id(channel_input)
    if not channel_id:
        return []

    time.sleep(random.uniform(0.2, 0.4))
    url = f"https://api.chzzk.naver.com/service/v1/channels/{channel_id}/videos?sortType=LATEST&pagingType=PAGE&page=0&size={page_size}"

    ua = random.choice(STEALTH_USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Referer": f"https://chzzk.naver.com/{channel_id}/videos",
        "Origin": "https://chzzk.naver.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            video_list = data.get("content", {}).get("data", []) or []

            results = []
            for item in video_list:
                video_no = item.get("videoNo")
                title = item.get("videoTitle") or "Untitled Stream"
                duration_sec = item.get("duration", 0)
                pub_date = item.get("publishDate", "")
                vod_url = (
                    f"https://chzzk.naver.com/video/{video_no}" if video_no else ""
                )

                hours = duration_sec // 3600
                minutes = (duration_sec % 3600) // 60
                dur_str = f"{hours}시간 {minutes}분" if hours > 0 else f"{minutes}분"
                date_str = pub_date[:10] if len(pub_date) >= 10 else ""

                channel_info = item.get("channel", {}) or {}
                channel_name = channel_info.get("channelName", "")

                results.append(
                    {
                        "video_no": str(video_no),
                        "title": title,
                        "duration_sec": duration_sec,
                        "duration_str": dur_str,
                        "publish_date": pub_date,
                        "date_str": date_str,
                        "vod_url": vod_url,
                        "channel_name": channel_name,
                    }
                )
            return results
    except Exception:
        return []


def fetch_chzzk_video_meta(video_input: str) -> dict[str, Any] | None:
    """Fetch metadata (title, publishDate, channel info, etc.) for a single Chzzk VOD."""
    video_no = extract_chzzk_video_no(video_input)
    if not video_no:
        return None
    try:
        url = f"https://api.chzzk.naver.com/service/v2/videos/{video_no}"
        ua = random.choice(STEALTH_USER_AGENTS)
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("content", {})
            title = content.get("videoTitle") or f"VOD_{video_no}"
            pub_date = content.get("publishDate", "") or ""
            date_str = re.sub(r"[^\d]", "", pub_date[:10]) if pub_date else ""
            channel_info = content.get("channel", {}) or {}
            channel_id = channel_info.get("channelId", "")
            channel_name = channel_info.get("channelName", "")
            return {
                "video_no": video_no,
                "title": title,
                "date_str": date_str,
                "publish_date": pub_date,
                "channel_id": channel_id,
                "channel_name": channel_name,
            }
    except Exception:
        return None


def get_chzzk_direct_audio_url(video_input: str) -> str | None:
    """Get direct audio stream URL or HLS playlist from Chzzk API with 144p/360p download acceleration."""
    video_no = extract_chzzk_video_no(video_input)
    if not video_no:
        return None

    try:
        meta_url = f"https://api.chzzk.naver.com/service/v2/videos/{video_no}"
        ua = random.choice(STEALTH_USER_AGENTS)
        req = urllib.request.Request(meta_url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("content", {})
            video_id = content.get("videoId")
            in_key = content.get("inKey")
            rewind_json_str = content.get("liveRewindPlaybackJson")

        # 1. Live Rewind HLS Stream (Auto-select 144p/360p audio chunklist for 30x faster download)
        if rewind_json_str:
            try:
                rewind_obj = json.loads(rewind_json_str)
                for m in rewind_obj.get("media", []):
                    path = m.get("path")
                    if path:
                        try:
                            from urllib.parse import urljoin

                            sub_req = urllib.request.Request(
                                path,
                                headers={
                                    "User-Agent": ua,
                                    "Referer": "https://chzzk.naver.com/",
                                },
                            )
                            with urllib.request.urlopen(sub_req, timeout=5) as sub_resp:
                                sub_content = sub_resp.read().decode("utf-8")
                                for line in sub_content.splitlines():
                                    line_s = line.strip()
                                    if "144p" in line_s and ".m3u8" in line_s:
                                        return urljoin(path, line_s)
                                for line in sub_content.splitlines():
                                    line_s = line.strip()
                                    if (
                                        "360p" in line_s or "480p" in line_s
                                    ) and ".m3u8" in line_s:
                                        return urljoin(path, line_s)
                        except Exception:
                            pass
                        return path
            except Exception as e:
                _logger.debug("Silenced exception: %s", e)

        # 2. Standard VOD Playback API (DASH / M4A / MP4)
        if video_id and in_key:
            playback_url = f"https://apis.naver.com/neonplayer/vodplay/v2/playback/{video_id}?key={in_key}"
            pb_req = urllib.request.Request(
                playback_url, headers={"User-Agent": ua, "Accept": "application/json"}
            )
            with urllib.request.urlopen(pb_req, timeout=10) as pb_resp:
                pb_data = json.loads(pb_resp.read().decode("utf-8"))
                periods = pb_data.get("period", [])

                m4a_url = None
                if periods:
                    for a in periods[0].get("adaptationSet", []):
                        reps = a.get("representation", [])
                        if reps and reps[0].get("baseURL"):
                            b_url = reps[0]["baseURL"][0]["value"]
                            if ".m4a" in b_url or "audio" in str(a.get("mimeType")):
                                return b_url
                            elif not m4a_url and (
                                ".mp4" in b_url or "144" in str(reps[0].get("id"))
                            ):
                                m4a_url = b_url
                if m4a_url:
                    return m4a_url
    except Exception as e:
        _logger.debug("Silenced exception: %s", e)

    return None


def get_chzzk_direct_lowres_video_url(video_input: str) -> str | None:
    """Get ultra-low-resolution (144p/360p) direct video stream URL for zero-disk visual face tracking."""
    video_no = extract_chzzk_video_no(video_input)
    if not video_no:
        return None

    try:
        meta_url = f"https://api.chzzk.naver.com/service/v2/videos/{video_no}"
        ua = random.choice(STEALTH_USER_AGENTS)
        req = urllib.request.Request(meta_url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("content", {})
            video_id = content.get("videoId")
            in_key = content.get("inKey")
            rewind_json_str = content.get("liveRewindPlaybackJson")

        # 1. Live Rewind HLS Stream
        if rewind_json_str:
            try:
                rewind_obj = json.loads(rewind_json_str)
                for m in rewind_obj.get("media", []):
                    if m.get("path"):
                        return m["path"]
            except Exception as e:
                _logger.debug("Silenced exception: %s", e)

        # 2. Standard VOD Playback API
        if video_id and in_key:
            playback_url = f"https://apis.naver.com/neonplayer/vodplay/v2/playback/{video_id}?key={in_key}"
            pb_req = urllib.request.Request(
                playback_url, headers={"User-Agent": ua, "Accept": "application/json"}
            )
            with urllib.request.urlopen(pb_req, timeout=10) as pb_resp:
                pb_data = json.loads(pb_resp.read().decode("utf-8"))
                periods = pb_data.get("period", [])

                if periods:
                    for a in periods[0].get("adaptationSet", []):
                        if "video" in str(a.get("mimeType")):
                            reps = a.get("representation", [])
                            for r in reps:
                                r_id = str(r.get("id", "")).lower()
                                if (
                                    "144" in r_id or "360" in r_id or "480" in r_id
                                ) and r.get("baseURL"):
                                    return r["baseURL"][0]["value"]
                            if reps and reps[0].get("baseURL"):
                                return reps[0]["baseURL"][0]["value"]
    except Exception as e:
        _logger.debug("Silenced exception: %s", e)

    return None

