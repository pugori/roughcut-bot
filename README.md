# 🎬 ChannelDNA Studio

<p align="center">
  <a href="https://pugori.github.io/channeldna-studio/"><strong>🌐 공식 웹사이트 바로가기</strong></a> •
  <a href="https://github.com/pugori/roughcut-bot/releases/latest"><strong>📦 최신 버전 다운로드</strong></a>
</p>

<p align="center">
  <img src="docs/preview.jpg" alt="ChannelDNA Studio Interface Preview" width="850">
</p>

---

## ✨ 주요 기능

- **🎯 스트리머 맞춤형 편집 스타일 프로파일링**: 레퍼런스로 삼고 싶은 유튜브 링크만 입력하면, 해당 유튜버의 발화 템포, 텐션 간격, 여백(오디오 호흡) 패턴을 딥러닝으로 자동 추출해 '맞춤형 편집 프로필'을 생성합니다.
- **✂️ VOD 초고속 AI 컷 편집**: 생성된 프로필을 내 영상에 적용하여, 루즈한 대기 시간과 침묵 구간을 자동으로 컷팅하고 핵심 텐션 구간만 촘촘하게 압축된 가편집 시퀀스를 생성합니다.
- **💬 시퀀스 동기화 자막 (Sequence-Synced SRT)**: 원본 영상 기준이 아닌, **'컷 편집이 완료된 타임라인'**에 수학적으로 완벽하게 싱크를 맞춘 SRT 자막 파일을 생성합니다. 
- **👥 화자 분리 자막 트랙 생성**: 음성 분석을 통해 다수의 화자(합방)를 분리하여 대화형 자막을 자동 구성합니다.
- **📄 편집기 원클릭 연동**: Premiere Pro(XML) 및 DaVinci Resolve(FCPXML) 호환 포맷을 동시 지원하여, 드래그 앤 드롭만으로 본편집 준비가 끝납니다.
- **🔒 로컬 보안 샌드박스**: 원본 동영상 파일이 외부로 전송되지 않으며, 사용자 로컬 PC (GPU 가속) 환경에서 독립적으로 실행됩니다.

---

## 🚀 빠른 시작 가이드 (Workflow)

ChannelDNA Studio는 다음의 흐름으로 작동합니다.

### 1단계: 프로필 생성 (Profile)
1. **[프로필 탭]**으로 이동합니다.
2. 편집 스타일을 추출하고 싶은 유튜브 영상 링크를 입력하고 분석을 시작합니다. (UI상으로는 '발화 스타일 분석'으로 표시됩니다)
3. 추출이 완료되면 원하는 이름(예: `침착맨 스타일`, `우왁굳 합방 텐션`)으로 프로필을 저장합니다.

### 2단계: 자동 컷 편집 시작 (Scan)
1. **[가편집 탭]**에서 내 원본 영상 파일(`.mp4`, `.mkv` 등)을 선택합니다.
2. 앞서 저장해둔 **[맞춤형 프로필]**을 선택하여 해당 텐션 리듬을 내 영상에 적용합니다.
3. **[출력 파일 선택]** 체크박스에서 필요한 포맷(Premiere XML, FCPXML, SRT 자막)을 미리 선택합니다.
4. **[자동 컷 편집 시작]** 버튼을 누릅니다.
5. *작업이 시작되면, 진행 상태와 자막 전사 내역이 모래시계가 아닌 **실시간 퍼센트 및 로그**로 표시되어 작업 상황을 직관적으로 확인할 수 있습니다.*

### 3단계: 편집기 연동
1. 작업이 끝나면 생성된 폴더가 자동으로 열립니다.
2. **XML(또는 FCPXML) 파일**을 Premiere Pro나 DaVinci Resolve로 불러옵니다. (1차 가편집 완료)
3. 불러온 시퀀스 타임라인 위에 **SRT 파일**을 자막 트랙으로 얹어줍니다. 컷 편집된 시퀀스 길이에 완벽하게 맞춰진 자막이 자동 세팅됩니다!

---

<p align="center" style="font-size: 11px; color: #888;">
  © 2026 ChannelDNA Project. All rights reserved.<br>
  Adobe®, Premiere Pro®는 Adobe Inc.의 등록 상표이며, DaVinci Resolve®는 Blackmagic Design Pty. Ltd.의 등록 상표입니다.<br>
  본 소프트웨어는 공개 표준 XML 포맷 호환성을 지원하는 독립 보조 도구입니다.
</p>
