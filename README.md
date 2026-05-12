# IREN News Monitor

IREN(NASDAQ: IREN) 의 보도자료 RSS 피드를 GitHub Actions가 5분 간격으로 폴링하여, 새 글이 올라오면 한국어 요약 + 영문 발췌 + 발표 시각 + 원문 링크를 Gmail로 발송합니다.

## 동작 방식

1. `.github/workflows/monitor.yml` 이 5분마다 (`*/5 * * * *`) `monitor.py` 실행
2. RSS (`https://irisenergy.gcs-web.com/rss/news-releases.xml`) 가져와 모든 `<item>` 파싱
3. `state/seen.json` 의 `seen_guids` 와 비교하여 신규 글만 추출
4. 각 신규 글마다:
   - Claude Haiku 4.5 로 한국어 2~3문장 요약 생성
   - Gmail SMTP (smtp.gmail.com:587) 로 HTML 메일 발송
   - 발송 성공 시 `seen_guids` 에 guid 추가 후 `state/seen.json` 저장
5. 워크플로 종료 직전, `seen.json` 이 변경됐다면 자동 커밋 & 푸시 (다음 실행이 동일 글 재발송하지 않도록)

한 실행에서 최대 5개까지만 발송 (storm 방지).

## 필수 Secrets

레포 Settings → Secrets and variables → Actions 에서 등록:

| Secret | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic 콘솔 발급 키 (sk-ant-...) |
| `GMAIL_USER` | 발신용 Gmail 주소 (예: thecruies@gmail.com) |
| `GMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 16자 (공백 제거) |
| `RECIPIENTS` | 수신자 콤마 구분 (예: a@x.com,b@y.com) |

`GMAIL_USER`, `GMAIL_APP_PASSWORD`, `RECIPIENTS` 는 초기 설정 시 `gh secret set` 으로 미리 등록됨.
`ANTHROPIC_API_KEY` 는 보안상 수동으로 추가해야 함.

## 수동 실행

GitHub 레포 → Actions 탭 → "IREN News Monitor" → "Run workflow" 클릭.
처음 한 번 수동 실행해서 secrets 설정이 정확한지 확인 권장.

## 중지 / 재개

- **일시 중지**: Actions 탭 → "IREN News Monitor" 워크플로 → `...` → "Disable workflow"
- **재개**: 같은 메뉴에서 "Enable workflow"
- **완전 제거**: `.github/workflows/monitor.yml` 삭제 또는 레포 삭제

## 간격 변경

`.github/workflows/monitor.yml` 의 `cron` 값 변경 후 커밋:
- 5분 간격: `*/5 * * * *` (GitHub Actions 권장 최소)
- 15분 간격: `*/15 * * * *`
- 매시 정각: `0 * * * *`

> 참고: GitHub Actions cron 은 부하 상황에 따라 5~15분 지연될 수 있습니다.

## 상태 초기화

`state/seen.json` 의 `seen_guids` 를 `[]` 로 비우거나 `first_run` 을 `true` 로 설정하면, 다음 실행에서 현재 모든 글을 "이미 본 것"으로 재시드하고 메일은 보내지 않습니다.
