# macOS 어댑터 설치와 실기 확인

v0.4는 PyObjC / ApplicationServices 접근성(AX) 어댑터를 제공합니다.
**Mac 카카오톡 실기 미검증이며, 설치만으로 바로 동작하는 지원은 아닙니다.**
현재 Windows에서 구현·가짜 AX 트리 테스트를 수행했습니다. Mac 카카오톡이 필요한
요소를 AX로 공개하지 않으면 이 방식으로 조작할 수 없으며 별도 구현이 필요합니다.

## 지원 범위

| 기능 | Mac 구현 및 조건 |
| --- | --- |
| MCP 시작·capabilities | UI 권한 없이 실행 가능 |
| 게시판 초안 작성·조회 | 수동으로 연 정확한 방/게시판 창, AXValue 쓰기 가능한 편집기 필요 |
| 게시판 읽기·검색 | AXRows의 각 행에 **전체 본문**이 노출되는 경우만 가능; 스크롤·상세창 탐색 미구현 |
| 등록 전 미리보기·검증 | 기존 5분 만료 일회용 토큰, 방·편집기·본문 재검증 공유 |
| 실제 등록 | 정확한 등록 버튼 AXPress 한 번; 성공 자동 판정 미구현, `published: null` 반환 |
| 일반 채팅·이미지·모니터링 | Windows 전용, Mac 호출은 미지원 오류 |

Windows 어댑터와 기존 채팅 구현은 변경하지 않았습니다. Linux는 공통 서비스만 지원합니다.
Mac에서는 게시판/작성 화면이 별도 창으로 전환되거나 목록에 요약만 공개될 경우,
선택자 보정만으로 해결되지 않을 수 있습니다. 실제 AX 구조 확인 후 어댑터 확장이 필요합니다.

## 설치

Python 3.11 이상을 권장합니다(전역 등록 스크립트의 tomllib 요구).

```sh
git clone https://github.com/YGJangontact/kakaotalk-mcp.git
cd kakaotalk-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/register_codex_mcp.py
```

이미 전역 등록된 경우 스크립트가 덮어쓰지 않습니다. 기존 `~/.codex/config.toml`의
command/cwd를 이 checkout으로 연결합니다. MCP 환경 설정에 다음을 추가합니다.

```toml
[mcp_servers.kakaotalk.env]
PYTHONUTF8 = "1"
KAKAO_MAC_PROFILE = "/absolute/path/kakao-mac-profile.json"
```

시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용에서 실제 MCP 실행 주체
(Codex/터미널/Python, macOS가 요청하는 항목)의 접근성을 허용하고 재시작합니다.
서버는 권한을 자동 요청하거나 설정을 바꾸지 않습니다.

## 선택자 보정

아래 JSON은 **구조 예시이며 실제 KakaoTalk 식별자가 아닙니다**. bundle ID는
설치된 KakaoTalk.app의 Info.plist `CFBundleIdentifier`로 확인합니다.
`room_window`는 정확한 방 이름을 강제하며 동명 창이 둘이면 중단합니다.

```json
{
  "bundle_id": "REPLACE_WITH_INSTALLED_BUNDLE_ID",
  "selectors": {
    "room_window": {"AXRole": "AXWindow", "AXTitle": "{room}"},
    "board": {"AXRole": "AXGroup", "AXIdentifier": "REPLACE_BOARD"},
    "compose": {"AXRole": "AXButton", "AXIdentifier": "REPLACE_COMPOSE"},
    "editor": {"AXRole": "AXTextArea", "AXIdentifier": "REPLACE_POST_EDITOR"},
    "publish": {"AXRole": "AXButton", "AXIdentifier": "REPLACE_PUBLISH"},
    "post_list": {"AXRole": "AXTable", "AXIdentifier": "REPLACE_LIST"},
    "post_body": {"AXRole": "AXStaticText", "AXIdentifier": "REPLACE_FULL_BODY"}
  }
}
```

AXIdentifier가 없으면 AXTitle/AXDescription의 **정확한 값**을 사용합니다.
선택자는 AXRole과 추가 속성 하나 이상이 필수입니다. 정규식·부분일치·좌표 대체는 없습니다.
본문 편집기와 댓글 입력기를 구분하고 등록 버튼을 게시판 영역 안에서 유일하게 지정해야 합니다.

```sh
export KAKAO_MAC_PROFILE=/absolute/path/kakao-mac-profile.json
.venv/bin/python scripts/diagnose_macos.py --room '테스트방'
# 제목/설명이 꼭 필요한 로컬 보정 시에만:
.venv/bin/python scripts/diagnose_macos.py --room '테스트방' --include-labels
```

진단은 UI를 조작하지 않고 AXRole/AXIdentifier를 출력합니다. AXValue는 출력하지 않습니다.
`--include-labels`는 방 이름·게시글 내용이 포함될 수 있으므로 출력을 Git에 올리지 마세요.
Xcode Accessibility Inspector로 계층과 AXPress/AXValue 쓰기 지원도 확인할 수 있습니다.

## Mac에서 직접 확인할 체크리스트

- [ ] macOS·칩셋·카카오톡·Python 버전 기록, framework 설치와 MCP 시작 확인.
- [ ] 권한 거부 시 명확한 오류, 허용 후 AXWindows/AXChildren 접근 확인.
- [ ] 지정된 테스트방을 직접 열고 방/게시판/작성 화면의 실제 AX 구조 보정.
- [ ] 동명 창과 댓글 입력기 때문에 잘못된 요소를 선택하지 않는지 확인.
- [ ] 빈 편집기에 한글·여러 줄·이모지 입력 후 원문 일치, 동일 초안 재호출 시 중복 없음.
- [ ] 다른 기존 초안 보존, 편집기 미노출/읽기 전용이면 입력하지 않는지 확인.
- [ ] 목록 AXRows 순서와 전체 본문 노출 여부 확인. 요약만 보이면 읽기 지원으로 판정하지 않기.
- [ ] 검색/새로고침/캐시 결과, 목록 범위를 넘는 오류 확인.
- [ ] 등록 미리보기 후 본문 변경·창 닫기·앱 재시작 시 확인값 무효화 확인.
- [ ] `kakao_check_board_publish`까지 실행하고 **등록 버튼은 누르지 않기**.

현재 사용자 지정 검증 범위는 실제 등록 직전까지입니다. 실제 등록·첨부·공지·댓글,
Mac UI 전환 완료·등록 결과 판정은 검증하지 않았습니다. 향후 실제 등록 테스트에는
별도 명시적 요청이 필요하며, `published: null` 결과를 자동 재시도해서는 안 됩니다.

API 근거: [Apple AXUIElementCopyAttributeValue](https://developer.apple.com/documentation/applicationservices/1462085-axuielementcopyattributevalue),
[AXUIElementPerformAction](https://developer.apple.com/documentation/applicationservices/1462091-axuielementperformaction).
