# 🧬 ChannelDNA: 역설계 기반 채널 편집 가이드 엔진 (MVP)

유튜브에 업로드된 검증된 편집 완성본을 역설계(Reverse Engineering)하여 채널 고유의 편집 템포와 텐션 규칙(DB)을 도출하고, 치지직 원본 롱폼 VOD에 대조하여 70~80% 정확도의 NLE 타임라인 마커(Premiere XML, DaVinci EDL, JSON)를 자동 생성하는 로컬 기반 보조 소프트웨어입니다.

---

## ✨ 핵심 기능

1. **완성본 영상 역설계 (`extractor.py`)**
   - 유튜브 URL 다운로드 (`yt-dlp`) 또는 로컬 완성본 비디오 파일 직접 분석
   - `PySceneDetect` 기반 프레임 다운샘플링 컷 전환점 및 평균 컷 지속 시간(ASL) 추출
   - `faster-whisper` CPU int8 양자화 기반 단어/문장 타임코드 전사
   - `librosa` 1kHz~3.5kHz 보컬 텐션 대역 밴드패스 필터링 및 z-score 정규화

2. **채널 Baseline DB 모델러 (`modeler.py`, `db.py`)**
   - $N$편의 영상 데이터를 0~100% 정규화 시간축으로 앙상블
   - FFT(고속 푸리에 변환) 기반 지배적 텐션 폭발 주기(초) 도출
   - SQLite 기반 채널 프로필 영구 저장 및 수동 파라미터 튜닝 지원

3. **대용량 VOD 스트리밍 스캐너 (`scanner.py`, `audio_engine.py`)**
   - FFmpeg 10분 단위 청크 제너레이터로 **메모리 점유율 200MB 이하 유지** (8시간 이상 VOD 완벽 지원)
   - VAD-Gated 텐션 스코어링 (게임 효과음/SFX 오탐 방지)
   - 발화 경계 스냅 및 실무 편집 완충 버퍼 적용 (시작점 `-3.0초`, 종료점 `+2.0초`)
   - 2초 미만 인접 마커 자동 병합
   - 재스캔 1초 완료를 위한 로컬 캐시 레이어 (`.npz`)

4. **NLE 타임라인 다중 포맷 내보내기 (`exporter.py`)**
   - **Adobe Premiere Pro XML** (`.xml`, FCP 7 호환)
   - **DaVinci Resolve EDL** (`.edl`, CMX 3600 표준)
   - **구조화 마커 JSON** (`.json`, 타임코드, 텐션 z-score, 사유 포함)

5. **현대적인 데스크톱 GUI & 헤드리스 CLI 제공**
   - **GUI**: CustomTkinter 기반 다크 모드, 실시간 타임라인 히트맵, 비동기 스레드 및 작업 취소 기능
   - **CLI**: Rich & Click 기반 터미널 원클릭 파이프라인

---

## 🚀 실행 방법

### 1. GUI 데스크톱 앱 실행 (권장)
```bash
python app.py
```
- **탭 1**: 유튜브 URL 또는 로컬 편집본 파일을 분석하여 DB에 적재
- **탭 2**: 채널 Baseline 프로필을 생성/조회하고 필요시 파라미터 튜닝
- **탭 3**: 치지직/로컬 원본 VOD를 선택하고 스캔 후 Premiere XML / DaVinci EDL / JSON 파일로 원클릭 내보내기

### 2. CLI 명령어 실행
```bash
# 1) 단일 유튜브 또는 로컬 완성본 영상 분석
python -m channel_dna.cli extract "https://www.youtube.com/watch?v=..." --channel "MyStreamer" --url

# 2) 수집된 데이터로 채널 프로필 생성
python -m channel_dna.cli build-profile "MyStreamer"

# 3) 원본 VOD 스캔 및 프리미어 XML 내보내기
python -m channel_dna.cli scan "C:/VODs/raw_stream.mp4" --channel "MyStreamer" --format xml

# 4) 가상 합성 데이터를 활용한 파이프라인 즉시 데모 실행
python -m channel_dna.cli demo
```

### 3. 단위 테스트 실행
```bash
python -m pytest -v
```

---

## 📂 프로젝트 구조

```
c:/dna/
├── app.py                      # CustomTkinter GUI 실행 진입점
├── requirements.txt           # 패키지 의존성 명세
├── README.md                  # 프로젝트 안내서
├── channel_dna/
│   ├── config.py              # 전역 설정 (버퍼 -3s/+2s, 윈도우, CPU 스레드)
│   ├── cli.py                 # Rich/Click CLI 인터페이스
│   ├── core/
│   │   ├── models.py          # Dataclass 정의 (Metadata, Profile, Marker 등)
│   │   ├── db.py              # SQLite Repository (CRUD)
│   │   ├── audio_engine.py    # 스트리밍 청킹, 밴드패스 필터, VAD 텐션, 캐싱
│   │   ├── extractor.py       # yt-dlp + PySceneDetect + Whisper + Librosa 분석
│   │   ├── modeler.py         # ASL 통계, FFT 텐션 주기, 프로필 DB 저장
│   │   ├── scanner.py         # 스트리밍 VOD 스캔, 문장 스냅, 완충 버퍼, 병합
│   │   ├── exporter.py        # Premiere XML / DaVinci EDL / Marker JSON 출력
│   │   ├── aligner.py         # (선택) RapidFuzz 대사 매핑 & 배속 추정
│   │   └── pipeline.py        # 비동기 백그라운드 Worker 및 Facade 계층
│   └── gui/
│       ├── main_window.py     # CustomTkinter 메인 윈도우
│       ├── views/             # 탭별 뷰 (extract, profiles, scan)
│       └── components/        # 재사용 위젯 (로그 콘솔, 프로그레스 카드, 타임라인 맵)
└── tests/
    ├── test_db.py
    ├── test_audio_engine.py
    ├── test_modeler.py
    ├── test_scanner.py
    ├── test_exporter.py
    └── test_aligner.py
```
