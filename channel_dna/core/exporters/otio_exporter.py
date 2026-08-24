"""Universal OpenTimelineIO (.otio) Exporter."""

from pathlib import Path

from channel_dna.core.models import ScanMarker


class OpenTimelineIOExporter:
    """Exports universal OpenTimelineIO (.otio) timelines supported across Premiere, DaVinci Resolve, Final Cut Pro, and Avid."""

    def export(
        self,
        markers: list[ScanMarker],
        vod_file_path: str,
        output_path: str,
        fps: float = 60.0,
        video_file_name: str | None = None,
    ) -> Path:
        import opentimelineio as otio

        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        clean_stem = (
            Path(video_file_name or vod_file_path).stem
            if (video_file_name or vod_file_path)
            else out_file.stem
        )
        vod_name = video_file_name or f"{clean_stem}.mp4"

        timeline = otio.schema.Timeline(name=f"ChannelDNA Timeline - {clean_stem}")
        track = otio.schema.Track(
            name="Rough Cut Video Track", kind=otio.schema.TrackKind.Video
        )
        timeline.tracks.append(track)

        rate = float(fps)
        for i, m in enumerate(markers, 1):
            dur_sec = max(0.1, m.end_time - m.start_time)
            start_frame = int(round(m.start_time * rate))
            duration_frames = max(1, int(round(dur_sec * rate)))

            time_range = otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(start_frame, rate),
                duration=otio.opentime.RationalTime(duration_frames, rate),
            )

            media_ref = otio.schema.ExternalReference(
                target_url=f"./{vod_name}",
                available_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(0, rate),
                    duration=otio.opentime.RationalTime(
                        int(round((m.end_time + 60.0) * rate)), rate
                    ),
                ),
            )

            clip = otio.schema.Clip(
                name=f"Cut {i:02d} (Peak {m.peak_tension:.1f}z)",
                media_reference=media_ref,
                source_range=time_range,
            )
            clip.markers.append(
                otio.schema.Marker(
                    name=f"Highlight {i:02d}",
                    marked_range=otio.opentime.TimeRange(
                        start_time=otio.opentime.RationalTime(start_frame, rate),
                        duration=otio.opentime.RationalTime(duration_frames, rate),
                    ),
                    color=otio.schema.MarkerColor.PURPLE
                    if m.peak_tension >= 3.0
                    else otio.schema.MarkerColor.GREEN,
                )
            )
            track.append(clip)

        otio.adapters.write_to_file(timeline, str(out_file))
        return out_file
