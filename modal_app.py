"""Modal.com Serverless GPU Worker for ChannelDNA VOD Analysis & Subtitle Pipeline.

Deploys on NVIDIA L4 GPU with 2-minute turn-around for 6-hour broadcasts.
Exports both Solo/Collab FCP7 XML & FCPXML alongside Sequence-Synced Smart Subtitles (SRT).
"""

import gc
import os
from typing import Any

try:
    import modal

    app = modal.App("channel-dna-cloud")

    def download_models():
        from faster_whisper import WhisperModel
        from kiwipiepy import Kiwi

        print(
            "[Build Time] Pre-downloading and baking Korean Whisper-Turbo into Docker image..."
        )
        try:
            WhisperModel(
                "deepdml/faster-whisper-large-v3-turbo-ct2",
                device="cpu",
                compute_type="int8",
            )
        except Exception as e:
            print(f"[Build Warning] Falling back to standard large-v3-turbo: {e}")
            WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
        print("[Build Time] Pre-initializing Kiwi Korean morphological analyzer...")
        Kiwi(num_workers=1)
        print("[Build Time] All AI models baked successfully!")

    # Define high-speed Cloud container environment with FFmpeg & CUDA
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("ffmpeg", "git")
        .pip_install(
            "torch>=2.1.0",
            "torchaudio>=2.1.0",
            "nvidia-cublas-cu12",
            "nvidia-cudnn-cu12",
            "aiohttp>=3.9.0",
            "psycopg2-binary>=2.9.0",
            "faster-whisper>=1.0.0",
            "kiwipiepy>=0.18.0",
            "librosa>=0.10.0",
            "soundfile>=0.12.1",
            "scipy>=1.11.0",
            "numba>=0.58.0",
            "requests>=2.31.0",
            "yt-dlp>=2024.1.0",
            "numpy>=1.24.0",
            "tqdm>=4.66.0",
            "pysubs2>=1.6.0",
            "cryptography>=42.0.0",
        )
        .env(
            {
                "LD_LIBRARY_PATH": "/usr/local/lib/python3.11/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib:/usr/local/lib/python3.11/site-packages/nvidia/cuda_runtime/lib:$LD_LIBRARY_PATH",
                "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
            }
        )
        .run_function(download_models)
        .add_local_python_source("channel_dna")
    )
except ImportError:
    app = None
    image = None


def process_chzzk_vod_local(
    vod_url_or_no: str,
    streamer_name: str = "",
    solo_profile: dict[str, Any] | None = None,
    collab_profile: dict[str, Any] | None = None,
    selected_mode: str = "solo",
) -> dict[str, Any]:
    """Local / CPU fallback function executed in standard Python environment without Modal GPU."""
    from channel_dna.core.pipeline import PipelineFacade

    facade = PipelineFacade()
    return facade.run_cloud_pipeline(
        vod_url_or_no=vod_url_or_no,
        streamer_name=streamer_name,
        solo_profile=solo_profile,
        collab_profile=collab_profile,
        selected_mode=selected_mode,
    )


if app:

    @app.function(
        image=image,
        gpu="L4",
        timeout=86400,
        cpu=4.0,
        memory=16384,
    )
    def process_chzzk_vod_cloud(
        vod_url_or_no: str,
        streamer_name: str = "",
        solo_profile: dict[str, Any] | None = None,
        collab_profile: dict[str, Any] | None = None,
        selected_mode: str = "solo",
    ) -> dict[str, Any]:
        """Serverless Cloud function executed on NVIDIA L4 GPU with dynamic DNA profile."""
        try:
            from channel_dna.core.pipeline import PipelineFacade

            facade = PipelineFacade()
            result = facade.run_cloud_pipeline(
                vod_url_or_no=vod_url_or_no,
                streamer_name=streamer_name,
                solo_profile=solo_profile,
                collab_profile=collab_profile,
                selected_mode=selected_mode,
            )
            return result
        finally:
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            gc.collect()

    @app.function(
        schedule=modal.Period(minutes=5),
        timeout=30,
    )
    def keep_render_bot_awake():
        """Periodically pings the Render Web Service every 5 minutes to prevent cold-sleep."""
        import urllib.request

        try:
            req = urllib.request.Request(
                "https://roughcut-bot.onrender.com/health",
                headers={"User-Agent": "RoughCut-KeepAlive/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(f"[KeepAlive Ping] Render status: {resp.status}")
        except Exception as e:
            print(f"[KeepAlive Ping Notice] {e}")
