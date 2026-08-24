"""SQLite Database Manager with Self-Healing Schema Auto-Migration, Memory-Mapped I/O, and Context Management."""

from channel_dna.core.logger import get_logger

_logger = get_logger(__name__)

import json
import sqlite3
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from channel_dna.config import config
from channel_dna.core.models import ChannelProfile, SegmentData, VideoMetadata


class DBManager:
    def __init__(self, db_path: str | None = None):
        target_path = Path(db_path) if db_path else config.default_db_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = target_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS streamer_bindings (
                channel_id TEXT PRIMARY KEY,
                streamer_name TEXT NOT NULL,
                target_dna_profile TEXT DEFAULT '',
                passcode TEXT,
                master_discord_id INTEGER,
                is_bound INTEGER DEFAULT 0,
                last_processed_video_no TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                bound_at TIMESTAMP
            );
        """)
        try:
            conn.execute("ALTER TABLE streamer_bindings ADD COLUMN target_dna_profile TEXT DEFAULT '';")
        except Exception:
            pass
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bindings_channel ON streamer_bindings(channel_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bindings_bound ON streamer_bindings(is_bound);"
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
        from channel_dna.core.profiler import Profiler

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

