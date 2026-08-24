"""Unit tests for Streamer Passcode Binding, 24/7 Watchlist, and Guide Generator."""

import pytest
from bot.discord_bot import generate_secure_passcode
from channel_dna.core.db import DBManager
from channel_dna.core.guide_generator import GuideGenerator


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_channel_dna.db"
    return DBManager(str(db_file))


def test_passcode_generation():
    code1 = generate_secure_passcode("양망두")
    assert len(code1) >= 8
    assert "-" in code1
    assert code1.startswith("YMDU-") or code1.startswith("CDNA-") or len(code1.split("-")[0]) > 0

    code2 = generate_secure_passcode(" 침착맨 ")
    assert "-" in code2


def test_streamer_passcode_lifecycle(temp_db):
    ch_id = "b3e262a2795f17734c149afc738ad250"
    st_name = "양망두"
    passcode = "YMDU-7749"

    # 1. Admin issues passcode
    assert temp_db.create_passcode_binding(ch_id, st_name, passcode) is True

    # 2. Check pending state
    all_bindings = temp_db.get_all_streamer_bindings()
    assert len(all_bindings) == 1
    assert all_bindings[0]["channel_id"] == ch_id
    assert all_bindings[0]["is_bound"] == 0
    assert all_bindings[0]["passcode"] == passcode

    # No active bindings yet
    assert len(temp_db.get_active_streamer_bindings()) == 0

    # 3. Invalid passcode verification attempt
    assert temp_db.verify_and_bind_passcode("WRONG-CODE", 123456789) is None

    # 4. Valid streamer verification
    res = temp_db.verify_and_bind_passcode(passcode, 123456789)
    assert res is not None
    assert res["channel_id"] == ch_id
    assert res["streamer_name"] == st_name
    assert res["master_discord_id"] == 123456789

    # 5. Check active bindings
    active = temp_db.get_active_streamer_bindings()
    assert len(active) == 1
    assert active[0]["master_discord_id"] == 123456789

    # 6. Re-use attempt with the same passcode MUST fail (passcode destroyed)
    assert temp_db.verify_and_bind_passcode(passcode, 999999999) is None

    # 7. Update VOD tracker
    assert temp_db.update_last_processed_video_no(ch_id, "1049281") is True
    active_after = temp_db.get_active_streamer_bindings()
    assert active_after[0]["last_processed_video_no"] == "1049281"

    # 8. Unbind streamer
    assert temp_db.unbind_streamer("양망두") is True
    assert len(temp_db.get_all_streamer_bindings()) == 0
    assert len(temp_db.get_active_streamer_bindings()) == 0


def test_guide_generator_corporate_memo():
    guide_text = GuideGenerator.generate_guide_text(
        vod_title="오늘은 카페 밀린거 읽으면서 수다떨기 ((00))",
        vod_date="20260824",
        total_markers=124,
    )
    assert "[방송 정보]" in guide_text
    assert "제목: 오늘은 카페 밀린거 읽으면서 수다떨기 ((00))" in guide_text
    assert "일시: 20260824" in guide_text
    assert "[중요: 원본 영상 파일명 설정]" in guide_text
    assert "👉 권장 파일명: 20260824_오늘은 카페 밀린거 읽으면서 수다떨기 ((00)).mp4" in guide_text
    assert "[파일 구성]" in guide_text
    assert "Solo (XML): 유튜브 개인 방송 분석을 바탕으로 생성된 파일" in guide_text
    assert "Collab (XML): 유튜브 합방 분석을 바탕으로 생성된 파일" in guide_text
    assert "자막 (SRT)" in guide_text
    assert "[사용 방법]" in guide_text
    assert "1. 원본 영상(mp4) 이름을 위의 권장 파일명과 동일하게 변경합니다." in guide_text
    assert "2. 영상과 전달된 파일들을 같은 폴더에 함께 배치합니다." in guide_text
    assert "3. 영상 편집 프로그램에서 해당 XML 파일을 불러옵니다." in guide_text
    assert "4. 타임라인 위에 SRT 자막 파일을 적용합니다." in guide_text
