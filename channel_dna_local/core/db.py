"""SQLite Database Manager with Self-Healing Schema Auto-Migration, Memory-Mapped I/O, and Context Management."""

from channel_dna_local.core.logger import get_logger

_logger = get_logger(__name__)

import json
import sqlite3
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from channel_dna_local.config import config
from channel_dna_local.core.models import ChannelProfile, SegmentData, VideoMetadata


class DBManager:
    def __init__(self, db_path: str | None = None):
        target_path = Path(db_path) if db_path else config.default_db_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = target_path
        self._init_db()

    def _get_connection(self) -> Any:
        import os
        supabase_uri = os.environ.get("SUPABASE_URI")
        if supabase_uri:
            return Psycopg2MockConnection(supabase_uri)
            
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA mmap_size = 268435456;")  # 256MB MMAP
        conn.execute("PRAGMA cache_size = -64000;")  # 64MB Cache
        return conn

    @contextmanager
    def _session(self) -> Generator[sqlite3.Connection, None, None]:
        """Provides a managed database connection context that automatically commits and closes."""
        conn = self._get_connection()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._session() as conn:
            self._create_tables(conn)
            self._apply_migrations(conn)

    def _create_tables(self, conn: sqlite3.Connection):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                duration REAL NOT NULL,
                avg_shot_length REAL NOT NULL,
                channel_name TEXT,
                file_path TEXT,
                video_type TEXT DEFAULT 'auto',
                speech_density REAL DEFAULT 0.75,
                laughter_score REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS segments (
                segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                duration REAL NOT NULL,
                rms_peak REAL NOT NULL,
                transcript TEXT,
                FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS channel_profiles (
                profile_id TEXT PRIMARY KEY,
                channel_name TEXT UNIQUE NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 1,
                avg_shot_length REAL NOT NULL DEFAULT 3.5,
                tension_interval REAL NOT NULL DEFAULT 45.0,
                silence_tolerance REAL NOT NULL DEFAULT 0.8,
                highlight_rms_threshold REAL NOT NULL DEFAULT 0.95,
                hook_duration REAL NOT NULL DEFAULT 15.0,
                custom_vocab TEXT DEFAULT '',
                motif_template TEXT,
                youtube_url TEXT DEFAULT '',
                chzzk_url TEXT DEFAULT '',
                profile_type TEXT DEFAULT 'all',
                host_voice_print TEXT,
                narrative_quota TEXT,
                speech_density_weight REAL DEFAULT 0.65,
                laughter_sensitivity REAL DEFAULT 1.20,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS marker_history (
                video_no TEXT PRIMARY KEY,
                channel_name TEXT NOT NULL,
                title TEXT NOT NULL,
                duration_sec INTEGER NOT NULL,
                marker_count INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                json_data TEXT,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_name);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_segments_video ON segments(video_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_segments_timing ON segments(video_id, start_time, end_time);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_marker_channel ON marker_history(channel_name);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_marker_scanned ON marker_history(scanned_at DESC);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_profile_name ON channel_profiles(channel_name);"
        )
        conn.commit()

    def _apply_migrations(self, conn: sqlite3.Connection):
        # 1. Videos migrations
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(videos);")
        v_cols = {r[1] for r in cur.fetchall()}
        if "video_type" not in v_cols:
            conn.execute("ALTER TABLE videos ADD COLUMN video_type TEXT DEFAULT 'auto';")
        if "speech_density" not in v_cols:
            conn.execute("ALTER TABLE videos ADD COLUMN speech_density REAL DEFAULT 0.75;")
        if "laughter_score" not in v_cols:
            conn.execute("ALTER TABLE videos ADD COLUMN laughter_score REAL DEFAULT 1.0;")

        # 2. Marker history migrations
        if "json_data" not in {r[1] for r in cur.execute("PRAGMA table_info(marker_history);").fetchall()}:
            conn.execute("ALTER TABLE marker_history ADD COLUMN json_data TEXT;")

        # 3. Channel profiles migrations
        cur.execute("PRAGMA table_info(channel_profiles);")
        p_cols = {r[1] for r in cur.fetchall()}
        required_cols = {
            "profile_id": "TEXT",
            "channel_name": "TEXT",
            "sample_count": "INTEGER DEFAULT 1",
            "avg_shot_length": "REAL DEFAULT 3.5",
            "tension_interval": "REAL DEFAULT 45.0",
            "silence_tolerance": "REAL DEFAULT 0.8",
            "highlight_rms_threshold": "REAL DEFAULT 0.95",
            "hook_duration": "REAL DEFAULT 15.0",
            "custom_vocab": "TEXT DEFAULT ''",
            "motif_template": "TEXT",
            "youtube_url": "TEXT DEFAULT ''",
            "chzzk_url": "TEXT DEFAULT ''",
            "profile_type": "TEXT DEFAULT 'all'",
            "host_voice_print": "TEXT",
            "narrative_quota": "TEXT",
            "speech_density_weight": "REAL DEFAULT 0.65",
            "laughter_sensitivity": "REAL DEFAULT 1.20",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        for col, col_type in required_cols.items():
            if col not in p_cols:
                conn.execute(f"ALTER TABLE channel_profiles ADD COLUMN {col} {col_type};")
        conn.commit()

    def record_marker_history(
        self,
        video_no: str,
        channel_name: str,
        title: str,
        duration_sec: int,
        marker_count: int,
        file_path: str,
        json_data: str = "{}",
    ):
        with self._session() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO marker_history (video_no, channel_name, title, duration_sec, marker_count, file_path, json_data, scanned_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (
                    str(video_no),
                    channel_name,
                    title,
                    duration_sec,
                    marker_count,
                    file_path,
                    json_data,
                ),
            )
            conn.commit()

    def get_marker_history(self, video_no: str) -> dict[str, Any] | None:
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM marker_history WHERE video_no = ?", (str(video_no),)
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def is_video_analysis_complete(self, conn: sqlite3.Connection, video_id: str) -> bool:
        """Checks if a video in DB has all required multi-feature fields (speech_density, laughter_score, mined lexicon/voiceprint, and non-empty segments)."""
        cur = conn.cursor()
        cur.execute(
            "SELECT speech_density, laughter_score, file_path FROM videos WHERE video_id = ?",
            (video_id,),
        )
        row = cur.fetchone()
        if not row:
            return False
        speech_density, laughter_score, file_path = row
        if speech_density is None or speech_density <= 0:
            return False
        if laughter_score is None or laughter_score <= 0:
            return False
        if not file_path or not str(file_path).strip():
            return False
        cur.execute("SELECT COUNT(*) FROM segments WHERE video_id = ?", (video_id,))
        seg_cnt = cur.fetchone()[0]
        return seg_cnt > 0

    def save_video_analysis(self, metadata: VideoMetadata, segments: list[SegmentData]):
        with self._session() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO videos (video_id, title, duration, avg_shot_length, channel_name, file_path, video_type, speech_density, laughter_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    metadata.video_id,
                    metadata.title,
                    metadata.duration,
                    metadata.avg_shot_length,
                    metadata.channel_name,
                    metadata.file_path,
                    metadata.video_type or "auto",
                    metadata.speech_density or 0.75,
                    metadata.laughter_score or 1.0,
                ),
            )

            conn.execute(
                "DELETE FROM segments WHERE video_id = ?", (metadata.video_id,)
            )

            seg_rows = [
                (
                    s.video_id,
                    s.start_time,
                    s.end_time,
                    s.duration,
                    s.rms_peak,
                    s.transcript,
                )
                for s in segments
            ]
            conn.executemany(
                """
                INSERT INTO segments (video_id, start_time, end_time, duration, rms_peak, transcript)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                seg_rows,
            )
            conn.commit()

    def update_video_type(self, video_id: str, new_type: str) -> bool:
        """Updates video_type ('solo', 'collab', 'auto') for a specific video."""
        with self._session() as conn:
            cur = conn.execute(
                "UPDATE videos SET video_type = ? WHERE video_id = ?",
                (new_type, video_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def get_all_videos(self) -> list[VideoMetadata]:
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT video_id, title, duration, avg_shot_length, channel_name, file_path, video_type, speech_density, laughter_score, created_at FROM videos ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
            return [VideoMetadata.from_row(r) for r in rows]

    def get_videos_by_channel(self, channel_name: str) -> list[VideoMetadata]:
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT video_id, title, duration, avg_shot_length, channel_name, file_path, video_type, speech_density, laughter_score, created_at
                FROM videos WHERE LOWER(channel_name) = LOWER(?) ORDER BY created_at DESC
            """,
                (channel_name,),
            )
            rows = cur.fetchall()
            return [VideoMetadata.from_row(r) for r in rows]

    def get_channel_names(self) -> list[str]:
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT channel_name FROM videos WHERE channel_name IS NOT NULL AND channel_name != ''"
            )
            v_names = [r["channel_name"] for r in cur.fetchall()]
            cur.execute(
                "SELECT DISTINCT channel_name FROM channel_profiles WHERE channel_name IS NOT NULL AND channel_name != ''"
            )
            p_names = [r["channel_name"] for r in cur.fetchall()]
            cur.execute(
                "SELECT DISTINCT channel_name FROM marker_history WHERE channel_name IS NOT NULL AND channel_name != ''"
            )
            m_names = [r["channel_name"] for r in cur.fetchall()]
            all_names = v_names + p_names + m_names
            clean_names = sorted(
                list(
                    set(
                        n.replace("_Solo", "").replace("_Collab", "").strip()
                        for n in all_names
                        if n and not n.startswith("🤖") and n != "(수집된 채널 없음)"
                    )
                )
            )
            return clean_names

    def get_video_by_id(self, video_id: str) -> VideoMetadata | None:
        """Retrieves a single video by video_id."""
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT video_id, title, duration, avg_shot_length, channel_name, file_path, video_type, speech_density, laughter_score, created_at FROM videos WHERE video_id = ?",
                (video_id,),
            )
            row = cur.fetchone()
            if row:
                return VideoMetadata.from_row(row)
            return None

    def recalculate_streamer_profiles(self, channel_name: str):
        """Helper to re-derive Two-Track profiles for a given streamer."""
        from channel_dna_local.core.profiler import Profiler

        profiler = Profiler(self)
        return profiler.derive_two_track_profiles(channel_name)

    def is_video_stored(self, video_id: str) -> bool:
        """Checks if a video is already stored in the SQLite videos table."""
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM videos WHERE video_id = ? LIMIT 1", (video_id,))
            return cur.fetchone() is not None

    def get_db_stats(self) -> dict[str, Any]:
        """Returns summary statistics of data currently stored in SQLite DB."""
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM videos")
            video_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM channel_profiles")
            profile_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM marker_history")
            marker_count = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(DISTINCT channel_name) FROM videos WHERE channel_name IS NOT NULL AND channel_name != ''"
            )
            channel_count = cur.fetchone()[0]
            return {
                "video_count": video_count,
                "profile_count": profile_count,
                "marker_count": marker_count,
                "channel_count": channel_count,
            }

    def get_segments_by_video(self, video_id: str) -> list[SegmentData]:
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT segment_id, video_id, start_time, end_time, duration, rms_peak, transcript
                FROM segments WHERE video_id = ? ORDER BY start_time ASC
            """,
                (video_id,),
            )
            rows = cur.fetchall()
            return [
                SegmentData(
                    segment_id=r["segment_id"],
                    video_id=r["video_id"],
                    start_time=r["start_time"],
                    end_time=r["end_time"],
                    duration=r["duration"],
                    rms_peak=r["rms_peak"],
                    transcript=r["transcript"],
                )
                for r in rows
            ]

    def save_profile(self, profile: ChannelProfile):
        motif_json = (
            json.dumps(profile.motif_template) if profile.motif_template else None
        )
        quota_json = (
            json.dumps(profile.narrative_quota) if profile.narrative_quota else None
        )
        with self._session() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO channel_profiles (
                    profile_id, channel_name, sample_count, avg_shot_length, tension_interval, silence_tolerance, highlight_rms_threshold, hook_duration, custom_vocab, motif_template, youtube_url, chzzk_url, profile_type, host_voice_print, narrative_quota, speech_density_weight, laughter_sensitivity, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (
                    profile.profile_id or str(uuid.uuid4())[:8],
                    profile.channel_name,
                    profile.sample_count,
                    profile.avg_shot_length,
                    profile.tension_interval,
                    profile.silence_tolerance,
                    profile.highlight_rms_threshold,
                    profile.hook_duration,
                    profile.custom_vocab or "",
                    motif_json,
                    profile.youtube_url or "",
                    profile.chzzk_url or "",
                    profile.profile_type or "all",
                    profile.host_voice_print,
                    quota_json,
                    profile.speech_density_weight if profile.speech_density_weight is not None else 0.65,
                    profile.laughter_sensitivity if profile.laughter_sensitivity is not None else 1.20,
                ),
            )
            conn.commit()

    def update_channel_urls(
        self,
        channel_name: str,
        youtube_url: str | None = None,
        chzzk_url: str | None = None,
    ):
        """Saves or updates streamer's YouTube and Chzzk channel URLs in SQLite DB for base and all derived profiles."""
        if not channel_name or channel_name == "(수집된 채널 없음)":
            return

        base_name = channel_name.replace("_Solo", "").replace("_Collab", "").strip()

        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM channel_profiles WHERE LOWER(channel_name) = LOWER(?)",
                (base_name,),
            )
            row = cur.fetchone()
            if row:
                curr_yt = row["youtube_url"] if "youtube_url" in row.keys() and row["youtube_url"] else ""
                curr_chzzk = row["chzzk_url"] if "chzzk_url" in row.keys() and row["chzzk_url"] else ""
                new_yt = youtube_url if youtube_url is not None else curr_yt
                new_chzzk = chzzk_url if chzzk_url is not None else curr_chzzk
                conn.execute(
                    "UPDATE channel_profiles SET youtube_url = ?, chzzk_url = ?, updated_at = CURRENT_TIMESTAMP WHERE profile_id = ?",
                    (new_yt, new_chzzk, row["profile_id"]),
                )
            else:
                prof_id = str(uuid.uuid4())[:8]
                conn.execute(
                    """
                    INSERT INTO channel_profiles (profile_id, channel_name, youtube_url, chzzk_url, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (prof_id, base_name, youtube_url or "", chzzk_url or ""),
                )

            if youtube_url is not None or chzzk_url is not None:
                if youtube_url is not None and chzzk_url is not None:
                    conn.execute(
                        "UPDATE channel_profiles SET youtube_url = ?, chzzk_url = ?, updated_at = CURRENT_TIMESTAMP WHERE LOWER(channel_name) LIKE LOWER(?) || '_%'",
                        (youtube_url, chzzk_url, base_name),
                    )
                elif youtube_url is not None:
                    conn.execute(
                        "UPDATE channel_profiles SET youtube_url = ?, updated_at = CURRENT_TIMESTAMP WHERE LOWER(channel_name) LIKE LOWER(?) || '_%'",
                        (youtube_url, base_name),
                    )
                elif chzzk_url is not None:
                    conn.execute(
                        "UPDATE channel_profiles SET chzzk_url = ?, updated_at = CURRENT_TIMESTAMP WHERE LOWER(channel_name) LIKE LOWER(?) || '_%'",
                        (chzzk_url, base_name),
                    )

            conn.commit()

    def get_profile(self, channel_name: str) -> ChannelProfile | None:
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT profile_id, channel_name, sample_count, avg_shot_length, tension_interval, silence_tolerance, highlight_rms_threshold, hook_duration, custom_vocab, motif_template, youtube_url, chzzk_url, profile_type, host_voice_print, narrative_quota, speech_density_weight, laughter_sensitivity, updated_at
                FROM channel_profiles WHERE LOWER(channel_name) = LOWER(?) OR LOWER(profile_id) = LOWER(?)
            """,
                (channel_name, channel_name),
            )
            r = cur.fetchone()
            if not r:
                cur.execute(
                    """
                    SELECT profile_id, channel_name, sample_count, avg_shot_length, tension_interval, silence_tolerance, highlight_rms_threshold, hook_duration, custom_vocab, motif_template, youtube_url, chzzk_url, profile_type, host_voice_print, narrative_quota, speech_density_weight, laughter_sensitivity, updated_at
                    FROM channel_profiles WHERE LOWER(channel_name) = LOWER(?) || '_solo' OR LOWER(channel_name) = LOWER(?) || '_collab'
                    ORDER BY sample_count DESC LIMIT 1
                """,
                    (channel_name, channel_name),
                )
                r = cur.fetchone()
                if not r:
                    return None

            return ChannelProfile.from_row(r)

    def get_all_profiles(self) -> list[ChannelProfile]:
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT profile_id, channel_name, sample_count, avg_shot_length, tension_interval, silence_tolerance, highlight_rms_threshold, hook_duration, custom_vocab, motif_template, youtube_url, chzzk_url, profile_type, host_voice_print, narrative_quota, speech_density_weight, laughter_sensitivity, updated_at
                FROM channel_profiles ORDER BY channel_name ASC
            """)
            rows = cur.fetchall()
            profiles = []
            for r in rows:
                profiles.append(ChannelProfile.from_row(r))
            return profiles

    def delete_video(self, video_id: str) -> bool:
        """Deletes a video and its segments from the database."""
        with self._session() as conn:
            conn.execute("DELETE FROM segments WHERE video_id = ?", (video_id,))
            cur = conn.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))
            return cur.rowcount > 0

    def delete_profile(self, channel_name: str) -> bool:
        """Deletes a profile from the database."""
        with self._session() as conn:
            cur = conn.execute(
                "DELETE FROM channel_profiles WHERE LOWER(channel_name) = LOWER(?) OR LOWER(channel_name) LIKE LOWER(?) || '_%'",
                (channel_name, channel_name),
            )
            return cur.rowcount > 0

    # =========================================================================
    # Streamer Passcode Binding & 24/7 Watchlist Methods
    # =========================================================================

    def create_passcode_binding(
        self,
        channel_id: str,
        streamer_name: str,
        passcode: str,
        target_dna_profile: str = "",
    ) -> bool:
        """Registers a new streamer binding with a single-use passcode and target DNA profile (Admin only)."""
        dna_prof = target_dna_profile.strip() if target_dna_profile else streamer_name.strip()
        with self._session() as conn:
            conn.execute(
                """
                INSERT INTO streamer_bindings (channel_id, streamer_name, target_dna_profile, passcode, is_bound)
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(channel_id) DO UPDATE SET
                    streamer_name = excluded.streamer_name,
                    target_dna_profile = excluded.target_dna_profile,
                    passcode = excluded.passcode,
                    is_bound = 0,
                    master_discord_id = NULL,
                    bound_at = NULL;
                """,
                (channel_id, streamer_name, dna_prof, passcode),
            )
            return True

    def verify_and_bind_passcode(
        self, passcode: str, discord_user_id: int
    ) -> dict[str, Any] | None:
        """Verifies a single-use passcode and binds the channel exclusively to the discord_user_id.

        Destroys the passcode immediately upon successful binding.
        """
        clean_code = passcode.strip()
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT channel_id, streamer_name, target_dna_profile, is_bound, master_discord_id
                FROM streamer_bindings
                WHERE passcode = ? AND is_bound = 0;
                """,
                (clean_code,),
            )
            row = cur.fetchone()
            if not row:
                return None

            ch_id = row["channel_id"]
            st_name = row["streamer_name"]
            dna_prof = row["target_dna_profile"] or st_name

            # Complete exclusive 1-to-1 binding and destroy passcode
            conn.execute(
                """
                UPDATE streamer_bindings
                SET master_discord_id = ?,
                    is_bound = 1,
                    passcode = NULL,
                    bound_at = CURRENT_TIMESTAMP
                WHERE channel_id = ?;
                """,
                (discord_user_id, ch_id),
            )

            return {
                "channel_id": ch_id,
                "streamer_name": st_name,
                "target_dna_profile": dna_prof,
                "master_discord_id": discord_user_id,
            }

    def get_active_streamer_bindings(self) -> list[dict[str, Any]]:
        """Returns all actively bound streamer channels for 24/7 background monitoring."""
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT channel_id, streamer_name, target_dna_profile, master_discord_id, last_processed_video_no, bound_at
                FROM streamer_bindings
                WHERE is_bound = 1 AND master_discord_id IS NOT NULL;
                """
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def get_all_streamer_bindings(self) -> list[dict[str, Any]]:
        """Returns all bindings including pending ones for Admin status view."""
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT channel_id, streamer_name, target_dna_profile, passcode, master_discord_id, is_bound, last_processed_video_no, created_at, bound_at
                FROM streamer_bindings
                ORDER BY created_at DESC;
                """
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def update_last_processed_video_no(
        self, channel_id: str, video_no: str
    ) -> bool:
        """Updates the last processed VOD video_no to prevent duplicate exports."""
        with self._session() as conn:
            cur = conn.execute(
                """
                UPDATE streamer_bindings
                SET last_processed_video_no = ?
                WHERE channel_id = ?;
                """,
                (video_no, channel_id),
            )
            return cur.rowcount > 0

    def get_binding_by_discord_user_id(
        self, discord_user_id: int
    ) -> dict[str, Any] | None:
        """Finds active streamer binding by master_discord_id."""
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT channel_id, streamer_name, target_dna_profile, master_discord_id, last_processed_video_no, bound_at
                FROM streamer_bindings
                WHERE master_discord_id = ? AND is_bound = 1;
                """,
                (discord_user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def unbind_streamer(self, channel_id_or_name: str) -> bool:
        """Unbinds or deletes a streamer from active monitoring (Admin only)."""
        clean = channel_id_or_name.strip()
        with self._session() as conn:
            cur = conn.execute(
                """
                DELETE FROM streamer_bindings
                WHERE channel_id = ? OR LOWER(streamer_name) = LOWER(?);
                """,
                (clean, clean),
            )
            return cur.rowcount > 0

    # =========================================================================
    # User Profile Sandbox (Private Isolated Storage - Anti-Copyright Claim)
    # =========================================================================

    def save_user_profile(
        self,
        discord_user_id: int,
        profile_name: str,
        solo_profile: dict[str, Any],
        collab_profile: dict[str, Any],
        chzzk_channel_url: str = "",
        profile_id: str | None = None,
    ) -> str:
        """Saves or updates a user's isolated 3+3 calibrated profile (Private Sandbox)."""
        pid = profile_id or f"prof_{uuid.uuid4().hex[:12]}"
        solo_json = json.dumps(solo_profile, ensure_ascii=False)
        collab_json = json.dumps(collab_profile, ensure_ascii=False)
        with self._session() as conn:
            conn.execute(
                """
                INSERT INTO user_profiles (profile_id, discord_user_id, profile_name, chzzk_channel_url, solo_profile_json, collab_profile_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(profile_id) DO UPDATE SET
                    profile_name = excluded.profile_name,
                    chzzk_channel_url = excluded.chzzk_channel_url,
                    solo_profile_json = excluded.solo_profile_json,
                    collab_profile_json = excluded.collab_profile_json,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (pid, discord_user_id, profile_name.strip(), chzzk_channel_url.strip(), solo_json, collab_json),
            )
        return pid

    def get_user_profiles(self, discord_user_id: int) -> list[dict[str, Any]]:
        """Retrieves all isolated profiles registered by a specific user."""
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT profile_id, discord_user_id, profile_name, chzzk_channel_url, solo_profile_json, collab_profile_json, created_at, updated_at
                FROM user_profiles
                WHERE discord_user_id = ?
                ORDER BY updated_at DESC;
                """,
                (discord_user_id,),
            )
            rows = cur.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["solo_profile"] = json.loads(item["solo_profile_json"])
                except Exception:
                    item["solo_profile"] = {}
                try:
                    item["collab_profile"] = json.loads(item["collab_profile_json"])
                except Exception:
                    item["collab_profile"] = {}
                results.append(item)
            return results

    def get_user_profile(self, profile_id: str) -> dict[str, Any] | None:
        """Retrieves a single isolated profile by profile_id."""
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT profile_id, discord_user_id, profile_name, chzzk_channel_url, solo_profile_json, collab_profile_json, created_at, updated_at
                FROM user_profiles
                WHERE profile_id = ?;
                """,
                (profile_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            item = dict(row)
            try:
                item["solo_profile"] = json.loads(item["solo_profile_json"])
            except Exception:
                item["solo_profile"] = {}
            try:
                item["collab_profile"] = json.loads(item["collab_profile_json"])
            except Exception:
                item["collab_profile"] = {}
            return item

    def delete_user_profile(self, profile_id: str, discord_user_id: int | None = None) -> bool:
        """Deletes an isolated profile (with optional owner verification)."""
        with self._session() as conn:
            if discord_user_id is not None:
                cur = conn.execute(
                    "DELETE FROM user_profiles WHERE profile_id = ? AND discord_user_id = ?;",
                    (profile_id, discord_user_id),
                )
            else:
                cur = conn.execute("DELETE FROM user_profiles WHERE profile_id = ?;", (profile_id,))
            return cur.rowcount > 0

    # =========================================================================
    # Credit & Usage Tracking Engine
    # =========================================================================

    def get_user_credits(self, discord_user_id: int) -> int:
        """Returns the current credit balance of a user."""
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT credits FROM user_credits WHERE discord_user_id = ?;",
                (discord_user_id,),
            )
            row = cur.fetchone()
            return row["credits"] if row else 0

    def add_user_credits(
        self,
        discord_user_id: int,
        amount: int,
        reason: str = "수동 충전",
        order_id: str = "",
    ) -> int:
        """Adds credits to a user and logs transaction. Returns new balance."""
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO user_credits (discord_user_id, credits, total_charged, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(discord_user_id) DO UPDATE SET
                    credits = credits + excluded.credits,
                    total_charged = total_charged + excluded.credits,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (discord_user_id, amount, max(0, amount)),
            )
            cur.execute(
                "SELECT credits FROM user_credits WHERE discord_user_id = ?;",
                (discord_user_id,),
            )
            new_bal = cur.fetchone()["credits"]
            conn.execute(
                """
                INSERT INTO credit_transactions (discord_user_id, amount, balance_after, reason, order_id)
                VALUES (?, ?, ?, ?, ?);
                """,
                (discord_user_id, amount, new_bal, reason, order_id),
            )
            return new_bal

    def deduct_user_credit(
        self,
        discord_user_id: int,
        reason: str = "가편집 분석",
        order_id: str = "",
    ) -> tuple[bool, int]:
        """Deducts 1 credit from a user. Returns (success, remaining_credits)."""
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT credits FROM user_credits WHERE discord_user_id = ?;",
                (discord_user_id,),
            )
            row = cur.fetchone()
            current = row["credits"] if row else 0
            if current < 1:
                return False, current
            
            new_bal = current - 1
            conn.execute(
                """
                UPDATE user_credits
                SET credits = ?, total_used = total_used + 1, updated_at = CURRENT_TIMESTAMP
                WHERE discord_user_id = ?;
                """,
                (new_bal, discord_user_id),
            )
            conn.execute(
                """
                INSERT INTO credit_transactions (discord_user_id, amount, balance_after, reason, order_id)
                VALUES (?, -1, ?, ?, ?);
                """,
                (discord_user_id, new_bal, reason, order_id),
            )
            return True, new_bal

    def get_daily_free_usage_count(self, discord_user_id: int, usage_date: str) -> int:
        """Returns the number of free quota uses for the given date (YYYY-MM-DD)."""
        with self._session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) as cnt
                FROM daily_usage_logs
                WHERE discord_user_id = ? AND usage_date = ? AND is_free_quota = 1;
                """,
                (discord_user_id, usage_date),
            )
            row = cur.fetchone()
            return row["cnt"] if row else 0

    def record_daily_usage(
        self,
        discord_user_id: int,
        is_free_quota: bool,
        video_no: str = "",
        usage_date: str | None = None,
    ):
        """Records a VOD execution in daily usage logs."""
        from datetime import datetime, timezone
        d_str = usage_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._session() as conn:
            conn.execute(
                """
                INSERT INTO daily_usage_logs (discord_user_id, usage_date, is_free_quota, video_no)
                VALUES (?, ?, ?, ?);
                """,
                (discord_user_id, d_str, 1 if is_free_quota else 0, video_no),
            )

    def get_user_credit_summary(self, discord_user_id: int, today_str: str) -> dict[str, Any]:
        """Provides a complete summary of VIP status, daily free quota, and credit balance."""
        is_vip = self.get_binding_by_discord_user_id(discord_user_id) is not None
        free_used = self.get_daily_free_usage_count(discord_user_id, today_str) if is_vip else 0
        free_remaining = max(0, 2 - free_used) if is_vip else 0
        credits = self.get_user_credits(discord_user_id)
        return {
            "discord_user_id": discord_user_id,
            "is_vip": is_vip,
            "free_used_today": free_used,
            "free_remaining_today": free_remaining,
            "credits": credits,
        }



import os
import psycopg2
from psycopg2.extras import DictCursor

class Psycopg2MockCursor:
    def __init__(self, cur):
        self._cur = cur
        self.rowcount = -1
    def execute(self, sql, parameters=None):
        sql = sql.replace('?', '%s')
        sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        if sql.strip().upper().startswith('PRAGMA'):
            return self
        try:
            self._cur.execute(sql, parameters)
            self.rowcount = self._cur.rowcount
            return self
        except psycopg2.errors.DuplicateColumn:
            # Ignore duplicate columns during migrations
            self._cur.connection.rollback()
            return self
        except Exception as e:
            print(f'[Postgres Execute Error] {e}')
            raise
    def fetchone(self):
        try: return self._cur.fetchone()
        except: return None
    def fetchall(self):
        try: return self._cur.fetchall()
        except: return []

class Psycopg2MockConnection:
    def __init__(self, uri):
        self._conn = psycopg2.connect(uri)
        self._conn.autocommit = False
    def cursor(self):
        return Psycopg2MockCursor(self._conn.cursor(cursor_factory=DictCursor))
    def execute(self, sql, parameters=None):
        cur = self.cursor()
        return cur.execute(sql, parameters)
    def commit(self): self._conn.commit()
    def close(self): self._conn.close()
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None: self.commit()
        else: self._conn.rollback()

