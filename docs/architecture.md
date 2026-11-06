# 구조와 플랫폼 지원

이 저장소는 [kronenz/kakaotalk-mcp](https://github.com/kronenz/kakaotalk-mcp)의
MIT 라이선스 fork입니다. 기존 채팅 도구에 게시판 작업과 테스트를 추가했습니다.

```text
src/kakao_mcp/
  server.py                 MCP 도구 정의와 인자 전달
  runtime.py                공유 서비스·잠금·플랫폼 초기화
  common.py                 OS와 무관한 문자열 처리
  board.py                  초안 보호·입력 후 본문 대조
  board_actions.py          검색 캐시·등록 미리보기·확인값 검증
  backends/
    __init__.py             플랫폼 선택과 미지원 환경 안내
    windows_board.py        Windows 톡게시판 UI 조작
    macos.py                실험적 macOS AX 게시판 어댑터·선택자 진단
    clipboard.py            서식 포함 클립보드 보존·복원
  controller.py             기존 Windows 채팅 도구 구현
  parser.py                 대화 문자열 파싱·링크 추출
  config.py                 기존 Windows 설정과 대기시간
  __main__.py               python -m kakao_mcp 진입점
tests/                      UI를 실제로 조작하지 않는 테스트
scripts/                    전역 등록·명시적 live 검증
docs/                       사용법과 검증 한계
.github/workflows/tests.yml Windows/macOS/Linux 공통 테스트
```

실행 흐름은 `MCP 클라이언트 → server → runtime의 서비스 → OS 어댑터 → 카카오톡`입니다.
`board.py`와 `board_actions.py`는 Win32를 import하지 않습니다. Windows 구현은
`backends/windows_board.py`에 격리하고 기존 채팅 구현은 필요할 때만 가져옵니다.

## Mac에서 가능한 범위

| 구분 | Windows | macOS | Linux |
| --- | --- | --- | --- |
| MCP 서버 시작·공통 로직 | 지원 | 지원 | 지원 |
| 톡게시판 UI | Windows 어댑터 | 실험적 AX 어댑터, 실기 미검증 | 미지원 |
| 기존 채팅·이미지·모니터링 | 지원 | 미지원 | 미지원 |

`pywin32`는 Windows에서만 설치합니다. `kakao_capabilities`는 대화를 읽지 않고
지원 범위를 알려줍니다. PyObjC는 macOS에만 설치하며 UI 호출 시 지연 import합니다.

Mac 어댑터는 `open_editor`, `read`, `write`, `find_editor`, `read_post`,
`draft_snapshot`, `publish`를 구현합니다. 실제 UI에 맞춘 선택자 프로필과 접근성
권한이 필요합니다. [Mac 설치·제약·실기 체크리스트](macos.md)에 별도로 정리했습니다.
등록 버튼 호출 결과는 성공을 추정하지 않고 `published: null`을 반환합니다.

## 속도와 정확성

게시판은 공개 서버 API 대신 화면을 조작하므로 최초 탐색에는 UI 전환 시간이
듭니다. 현재는 매번 탐색하는 대신 같은 방·같은 `max_posts` 범위의 본문을
30초 동안 메모리에 보관합니다. 검색어가 달라도 이 본문으로 검색할 수 있습니다.

- `cache_hit`, `cache_age_seconds`로 캐시 여부와 탐색 완료 이후 경과 시간을 표시.
- `refresh=true`면 항상 새 UI 탐색.
- 최대 8개 탐색 결과만 메모리에 보관. 파일·로그·Git에 본문 저장 안 함.
- 오류가 난 부분 탐색은 캐시하지 않음.
- 초안 작성 요청·등록 미리보기에서 해당 방 캐시 무효화.
- 등록 확인에는 캐시를 쓰지 않고 실제 편집기의 방·본문·창을 다시 검사.

전체 게시판의 동기화된 인덱스는 아닙니다. 검색 중 새 글이 생기거나 같은 본문이
반복되면 위치가 달라질 수 있습니다. 결과는 계속 `complete: false`로 표시합니다.
최초 탐색의 Home/Down 이동 비용과 일부 고정 대기는 유지했습니다. 실제 상태를
확인하지 않고 대기만 줄이는 최적화는 적용하지 않았습니다.

2026-11-06 Windows 실기 검사 1회에서 3개 게시글 새 탐색은 3.8031초,
같은 범위의 캐시 검색은 0.0123초였습니다. MCP 요청부터 응답까지의 시간이며,
일반적인 성능 보장이 아닙니다. 캐시 결과는 그 사이의 새 글을 포함하지 않습니다.
서식 텍스트가 들어 있는 클립보드에서도 같은 검증을 통과했습니다.

## 검증 구분

단위 테스트는 데스크톱 입력을 대체합니다. CI의 macOS/Linux 통과는 공통 계층의
호환성을 의미하며 카카오톡 UI 동작 검증이 아닙니다. 실제 Windows 검증은
`scripts/check_board_workflow.py --live`로 수행하며, 이 스크립트는 실제 등록
도구의 호출을 거부합니다. 실제 등록 성공은 별도의 사용자 승인하에 검증해야 합니다.
