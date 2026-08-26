# 🎬 ChannelDNA Studio (v2.0.0)

> **장시간 방송 VOD 자동 가편집 & 화자 분리 XML 생성 솔루션**

ChannelDNA Studio는 치지직, 트위치, 유튜브 등의 장시간 생방송 다시보기(VOD)를 분석하여 무음 구간을 자동으로 절삭하고, 스트리머와 게스트의 발화를 분리하여 비선형 영상 편집기(Premiere Pro, DaVinci Resolve)용 **Final Cut Pro XML(xmeml v4)** 및 **동기화 SRT 자막**을 생성하는 소프트웨어입니다.

---

## 📦 다운로드 및 실행 방법

### 1. 릴리즈 다운로드
- [GitHub Releases 최신 릴리즈](https://github.com/pugori/roughcut-bot/releases/latest)에서 **`ChannelDNA.exe`** (또는 `app.enc`)를 다운로드합니다.

### 2. 실행 및 가편집 워크스페이스
1. **`ChannelDNA.exe`** 실행
2. 편집할 로컬 VOD 영상 파일 선택 (`.mp4`, `.mkv`, `.mov`)
3. 스트리머 발화 프로필 및 방송 유형(`합방 모드` / `솔로 모드`) 선택
4. `[가편집 XML 생성 시작]` 클릭 ➔ 완료 후 생성된 타임라인 XML 파일을 비선형 편집기(NLE)로 드래그하여 본편집 진행

---

## 🌐 공식 웹사이트 및 제품 명세

- **공식 랜딩 페이지**: [https://pugori.github.io/roughcut-bot/](https://pugori.github.io/roughcut-bot/)
- **공식 기능 명세서**: [docs/PROJECT_SPECIFICATION.md](docs/PROJECT_SPECIFICATION.md)
- **시스템 기획 및 설계서**: [docs/SYSTEM_DESIGN_CREDIT_AND_CALIBRATION.md](docs/SYSTEM_DESIGN_CREDIT_AND_CALIBRATION.md)

---

## 🔒 보안 및 데이터 처리 원칙

- **인메모리(RAM) 보안 샌드박스**: 본 배포 패키지는 핵심 엔진 코드를 AES-256으로 암호화(`app.enc`)하여 제공하며, 런처 실행 시 하드디스크에 임의의 코드를 기록하지 않고 RAM 상에서만 안전하게 순간 복호화되어 구동됩니다.
- **100% 로컬 오프라인 연산**: 사용자의 원본 미디어 데이터는 외부 서버로 전송되지 않으며, 사용자 로컬 PC의 하드웨어 자원만을 사용하여 처리됩니다.

---

## 📄 상표권 및 호환성 고지

Adobe®, Adobe Premiere Pro®는 Adobe Inc.의 등록 상표이며, DaVinci Resolve®는 Blackmagic Design Pty. Ltd.의 등록 상표입니다. 본 소프트웨어는 해당 비선형 편집기(NLE)와의 시퀀스 데이터 호환성을 제공하기 위해 공개 표준 Final Cut Pro XML(xmeml v4) 포맷을 지원하는 독립 보조 도구이며, 해당 상표권자와 직접적인 제휴 또는 후원 관계가 없습니다.
