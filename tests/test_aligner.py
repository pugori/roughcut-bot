from channel_dna.core.aligner import VODAligner


def test_aligner_speed_ramp():
    aligner = VODAligner(match_threshold=70.0)

    # Raw speech took 4.0s ("안녕하세요 반갑습니다 여러분")
    raw_segments = [{"start": 10.0, "end": 14.0, "text": "안녕하세요 반갑습니다 여러분 오늘 방송 시작합니다"}]
    # Finished speech was speed-ramped / cut to 2.0s
    finished_segments = [{"start": 0.0, "end": 2.0, "text": "안녕하세요 반갑습니다 여러분"}]

    matches = aligner.align_transcripts(finished_segments, raw_segments)
    assert len(matches) == 1
    m = matches[0]
    assert m.similarity_score >= 70.0
    assert m.estimated_speed_ramp == 0.5  # 2.0s / 4.0s = 0.5
