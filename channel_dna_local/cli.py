"""Rich & Click CLI for ChannelDNA."""

from channel_dna_local.core.logger import get_logger

_logger = get_logger(__name__)

import sys
from pathlib import Path

# Force UTF-8 stdout for Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception as e:
        _logger.debug("Silenced exception: %s", e)

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

from channel_dna_local.core.models import ChannelProfile
from channel_dna_local.core.pipeline import PipelineFacade

console = Console(force_terminal=True, legacy_windows=False)


@click.group()
def cli():
    """ChannelDNA: Reverse Engineering Channel Editing Guide Engine CLI."""


@cli.command()
@click.argument("video_input")
@click.option(
    "--channel",
    "-c",
    default="DefaultChannel",
    help="Channel name to associate analysis with.",
)
@click.option("--url", "-u", is_flag=True, help="Set if video_input is a YouTube URL.")
def extract(video_input: str, channel: str, url: bool):
    """Analyze a finished YouTube or local video."""
    console.print(
        f"[bold cyan]Starting extraction for:[/] {video_input} (Channel: {channel})"
    )
    facade = PipelineFacade()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Analyzing...", total=100)

        def progress_cb(stage: str, pct: float, msg: str):
            progress.update(
                task, completed=int(pct * 100), description=f"[{stage}] {msg}"
            )

        try:
            result = facade.extractor.analyze(
                video_input=video_input,
                channel_name=channel,
                is_url=url,
                progress_cb=progress_cb,
            )
            facade.db.save_video_analysis(result.metadata, result.segments)

            console.print(
                f"[bold green][OK] Successfully analyzed:[/] {result.metadata.title}"
            )
            console.print(f" - Duration: {result.metadata.duration:.1f}s")
            console.print(
                f" - Average Shot Length (ASL): {result.metadata.avg_shot_length:.2f}s"
            )
            console.print(f" - Dialogue Segments: {len(result.segments)}")
            console.print(f" - Cut Transitions: {len(result.cut_timestamps)}")
        except Exception as e:
            console.print(f"[bold red]Error during extraction:[/] {e}")
            sys.exit(1)


@cli.command(name="build-profile")
@click.argument("channel_name")
def build_profile(channel_name: str):
    """Build channel baseline profile from accumulated DB analyses."""
    facade = PipelineFacade()
    try:
        profile = facade.profiler.build_profile(channel_name)
        console.print(
            f"[bold green][OK] Channel Baseline Profile generated for:[/] [yellow]{channel_name}[/]"
        )

        table = Table(title=f"Channel Profile: {channel_name}")
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="magenta")

        table.add_row("Sample Videos", str(profile.sample_count))
        table.add_row("Avg Shot Length (ASL)", f"{profile.avg_shot_length}s")
        table.add_row("Tension Interval", f"{profile.tension_interval}s")
        table.add_row("Silence Tolerance", f"{profile.silence_tolerance}s")
        table.add_row(
            "Highlight RMS Threshold", f"{profile.highlight_rms_threshold} (z-score)"
        )
        table.add_row("Hook Duration", f"{profile.hook_duration}s")

        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Error building profile:[/] {e}")
        sys.exit(1)


@cli.command()
@click.argument("vod_path")
@click.option(
    "--channel", "-c", default="DefaultChannel", help="Target channel profile."
)
@click.option("--output", "-o", default=None, help="Output file path.")
@click.option(
    "--format",
    "-f",
    "export_format",
    default="xml",
    type=click.Choice(["xml", "edl", "json"]),
    help="Export format.",
)
def scan(vod_path: str, channel: str, output: str, export_format: str):
    """Scan a raw VOD file against channel profile and export NLE markers."""
    facade = PipelineFacade()
    vod_p = Path(vod_path)
    if not vod_p.exists():
        console.print(f"[bold red]VOD file not found:[/] {vod_path}")
        sys.exit(1)

    profile = facade.db.get_profile(channel)
    if not profile:
        console.print(
            f"[yellow]No profile found for '{channel}'. Using default generic baseline.[/]"
        )
        profile = ChannelProfile(
            profile_id="default",
            channel_name=channel,
            sample_count=1,
            avg_shot_length=3.5,
            tension_interval=45.0,
            silence_tolerance=0.8,
            highlight_rms_threshold=1.2,
            hook_duration=15.0,
        )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning VOD...", total=100)

        def progress_cb(stage: str, pct: float, msg: str):
            progress.update(
                task, completed=int(pct * 100), description=f"[{stage}] {msg}"
            )

        markers = facade.scanner.scan(
            vod_path=str(vod_p),
            profile=profile,
            use_cache=True,
            progress_cb=progress_cb,
        )

    console.print(f"[bold green][OK] Generated {len(markers)} highlight markers![/]")

    # Print top markers table
    table = Table(title=f"Detected Markers Preview ({len(markers)} cuts)")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Start ~ End Timecode", style="cyan")
    table.add_column("Duration", justify="right", style="green")
    table.add_column("Peak Tension (z)", justify="right", style="magenta")
    table.add_column("Label", style="yellow")

    for i, m in enumerate(markers[:15], 1):
        table.add_row(
            str(i),
            f"{m.start_timecode} ~ {m.end_timecode}",
            f"{m.duration:.1f}s",
            f"{m.peak_tension:.2f}",
            m.label,
        )
    if len(markers) > 15:
        table.add_row("...", "...", "...", "...", f"(+{len(markers) - 15} more)")
    console.print(table)

    # Export
    if not output:
        output = str(vod_p.parent / f"{vod_p.stem}_markers.{export_format}")

    exported_path = facade.export_markers(
        markers, str(vod_p), output, export_format=export_format
    )
    console.print(
        f"[bold green][OK] File exported successfully to:[/] [underline cyan]{exported_path}[/]"
    )


@cli.command()
def demo():
    """Run self-contained end-to-end synthetic demo."""
    import tempfile

    import numpy as np
    import soundfile as sf

    console.print("[bold yellow][*] Running ChannelDNA Synthetic End-to-End Demo...[/]")
    facade = PipelineFacade()

    # 1. Create synthetic audio file
    temp_dir = Path(tempfile.mkdtemp(prefix="cdna_demo_"))
    demo_wav = temp_dir / "demo_vod.wav"
    sr = 16000
    dur_sec = 60.0
    t = np.linspace(0, dur_sec, int(sr * dur_sec))

    # Base background noise
    audio = 0.05 * np.random.randn(len(t))
    # Add high-tension shouted segment at 15s~25s (1500Hz harmonic) and 45s~52s (2200Hz)
    audio[int(15 * sr) : int(25 * sr)] += 0.6 * np.sin(
        2 * np.pi * 1500 * t[int(15 * sr) : int(25 * sr)]
    )
    audio[int(45 * sr) : int(52 * sr)] += 0.7 * np.sin(
        2 * np.pi * 2200 * t[int(45 * sr) : int(52 * sr)]
    )

    sf.write(str(demo_wav), audio, sr)
    console.print(f" - Generated synthetic 60s test VOD at: {demo_wav}")

    # 2. Build mock profile
    profile = ChannelProfile(
        profile_id="demo-p1",
        channel_name="DemoStreamer",
        sample_count=5,
        avg_shot_length=2.8,
        tension_interval=30.0,
        silence_tolerance=0.7,
        highlight_rms_threshold=1.0,
        hook_duration=12.0,
    )
    facade.db.save_profile(profile)

    # 3. Scan VOD
    markers = facade.scanner.scan(str(demo_wav), profile, use_cache=False)
    console.print(
        f" - Scanned synthetic audio, detected [bold green]{len(markers)}[/] markers."
    )
    for i, m in enumerate(markers, 1):
        console.print(
            f"   [{i}] {m.start_timecode} ~ {m.end_timecode} (Dur: {m.duration:.1f}s, Peak: {m.peak_tension:.2f})"
        )

    # 4. Export to XML & EDL & JSON
    xml_out = temp_dir / "demo_premiere.xml"
    edl_out = temp_dir / "demo_davinci.edl"
    json_out = temp_dir / "demo_markers.json"

    facade.export_markers(markers, str(demo_wav), str(xml_out), "xml")
    facade.export_markers(markers, str(demo_wav), str(edl_out), "edl")
    facade.export_markers(markers, str(demo_wav), str(json_out), "json")

    console.print(
        f"[bold green][OK] Demo Complete! All formats generated successfully in {temp_dir}[/]"
    )


if __name__ == "__main__":
    cli()

