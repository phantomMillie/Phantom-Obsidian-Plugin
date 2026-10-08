# Phantom Obsidian Framework

Phantom Obsidian vault 작업 방식(팬텀 플로우 · 정책 추출 · 용어집)을 **이 PC의 모든 코딩 에이전트**가 쓰게 하는 프레임워크. 개인용.

## 원칙

- **PC 종속.** 한 번 설치하면 어느 AI · 어느 작업 폴더 · 어느 세션에서든 같은 지침과 스킬이 로드된다. 세션 훅 · 환경변수 · 작업 폴더에 기대지 않는다
- **본체 = 표준 포맷.** 방법은 [Agent Skills](https://agentskills.io/specification)(`SKILL.md`), vault 규칙은 vault 루트 `AGENTS.md`. 특정 AI 전용 문법을 본체에 넣지 않는다
- **규칙 원본은 vault에 있다** — `AGENTS.md`, `팬텀 플로우.md`. 스킬은 절차 + 완료 검사만. 규칙이 바뀌면 원본만 고친다

## 구조

```
~/.phantom-obsidian/            프레임워크 홈 (PC에 하나)
├── config.json                 vault 경로 — PC 설정 (gitignore)
├── PHANTOM.template.md         전역 지침 원본 → install.sh 가 PHANTOM.md 생성 (gitignore)
├── skills/<이름>/SKILL.md       방법 원본
├── install.sh                  PC에 연결 / 해제
└── .claude-plugin/             Claude Code 플러그인 메타 (스킬만)
```

`install.sh` 가 만드는 연결:

```
~/.claude/CLAUDE.md    ┐
~/.gemini/GEMINI.md    ├─ 관리 블록 → PHANTOM.md   (전역 지침: vault 경로 · AGENTS.md 읽기 · 스킬 목록)
~/.codex/AGENTS.md     ┘  (Claude · Gemini 는 import, Codex 는 내용 복사)
~/.agents/skills/*     → skills/*                  (Codex · Gemini CLI · Copilot · Cursor · OpenCode)
Claude Code 플러그인    → 이 폴더                   (스킬)
```

관리 블록(`<!-- phantom-obsidian:start/end -->`) 밖 내용은 건드리지 않는다. 여러 번 돌려도 블록은 하나.

## 설정 (`config.json`)

vault 마다 다른 값은 전부 여기. 프레임워크 코드 · 스킬에는 `<키>` 만 있고, 실행할 때 `<vault>/<paths.키>` 로 읽는다.
`config.json` 은 gitignore — 이 PC 에만 있다. 형식은 `config.example.json`.

```
vault                 vault 절대 경로
paths.projects ...    PARA 폴더 (projects · areas · resources · archives · store)
paths.method_doc      팬텀 플로우 방법론 문서            (flow-draft · qa-promote)
paths.meetings        회의록 폴더                        (flow-draft)
paths.flow_output     플로우 · QA 문서 기본 위치          (flow-draft)
paths.qa_example      완성형 정책 QA 예시 (선택)          (qa-promote)
paths.glossary        용어집 폴더 · glossary_index 인덱스 (glossary-add · qa-promote)
paths.policy_index    정책 인덱스 문서                    (policy-extract)
paths.para_inbox      PARA 인박스 · para_history 이동 히스토리
paths.devlog_inbox    분류기가 프로젝트 사건을 넘길 인박스 · issue_inbox 이슈용
paths.keyword_rules   키워드 규칙 JSON (선택, LLM 힌트)
paths.spec_doc        PARA 규격서 (선택, 인박스 머리말 링크)
classify.*            폴백 프로젝트 이름 · 자료 주제에서 뺄 폴더
local.*               API 키 · LLM 명령 · Slack 웹훅 파일 위치 (vault 밖)
```

## 스킬

```
flow-draft     1단계  코드 → 🧭 소스 플로우 (분기형 mermaid, 모호한 곳 🧐)
   ↓
flow-fill      2단계  🧐 하나씩 채움 (본문 ↔ 📌 미확정 1:1)
   ↓  🧐 0개
qa-promote     3~5단계  ✅ 정책 QA (결정테이블 · 케이스ID · given · 자동화 매핑)

policy-extract  코드 정책 영역별 전수 → ✅/⚠️/🚫 + 파일:라인 + mermaid
glossary-add    용어집 3줄 고정 + 📖 인덱스 갱신
```

## 확인 상태 (2026-10-08)

| 도구 | 전역 지침 | 스킬 |
|---|---|---|
| Claude Code | `/tmp` 새 세션에서 vault 경로 답함 ✅ | 플러그인 등록 ✅ |
| Codex CLI 0.153.4 | `/tmp` 새 세션에서 vault 경로 답함 ✅ | 5개 인식 ✅ |
| Gemini CLI 0.59.0 | 미확인 — 계정 티어가 Gemini CLI 지원 종료(Antigravity 이관 안내)라 모델 호출 불가 | `gemini skills list` 5개 ✅ |
| Copilot · Cursor · OpenCode | 미설치 | 문서상 `~/.agents/skills` 지원 |

## 설치

```bash
git clone https://github.com/phantomMillie/Phantom-Obsidian-Plugin.git ~/.phantom-obsidian
cd ~/.phantom-obsidian
cp config.example.json config.json      # "vault" 값 수정
./install.sh
```

vault 경로를 바꾸거나 템플릿을 고치면 `./install.sh` 다시. 해제는 `./install.sh --remove`.

## vault 쪽 준비

- `AGENTS.md` — 규칙 원본 (Codex · Copilot · Cursor 가 vault 안에서 읽음)
- `CLAUDE.md` — `@AGENTS.md` 한 줄
- 전역 지침이 "vault 문서 쓰기 전에 `AGENTS.md` 읽기"를 걸어두므로, 작업 폴더가 vault 가 아니어도 규칙이 따라온다

## PARA 수집기

`para/collect.py` — AI 도구 대화 기록에서 **끝난 사건**만 골라 `<para_inbox>` 에 쌓는다.

```bash
python3 para/collect.py --dry-run            # 결과만 출력
python3 para/collect.py                      # 적립 (최근 24시간, 최대 20세션)
python3 para/collect.py --no-llm             # LLM 없이 끝 신호 기준 세션 단위
```

자동화 세션(`claude -p` · `codex exec`)은 건너뛴다. 진행 상태는 `state/` (gitignore).

## PARA 분류기

`para/classify.py` — `<para_inbox>` 의 사건을 규칙 → LLM → 폴백(`classify.fallback_project`)으로 보낸다. 결과는 `<para_history>` + Slack.

- 프로젝트 → `<devlog_inbox>` · `<issue_inbox>` 에 `[프로젝트|섹션] 원문` 으로 넘김. 그 인박스를 읽는 분배 배치가 개발일지 · 이슈 · 할 일에 넣는다
- Areas → `<areas>/🧵 <영역>.md` `## 🧠 메모`. 영역 노트가 없으면 PARA 인박스에 승인 체크박스 → 체크하면 다음 실행 때 생성
- Resources → `<resources>/<주제>/📎 <주제> 수집.md`

```bash
python3 para/classify.py --dry-run           # 판단만
python3 para/classify.py --no-slack          # 분류 (Slack 없이)
```

외부 LLM은 `para/llm.py` 의 `llm_allowed()` 가 허용할 때만 (API 키 또는 claude Team · Enterprise). 스케줄 · 교정 학습(Q14)은 아직 없음.

## 다음 층 (예정)

- 가드 — vault 린트 스크립트 + PC 단위 실행(launchd 감시 / git pre-commit). 어떤 AI가 쓰든, 손으로 고치든 같은 기준으로 걸림
- 이력 — git 자동 커밋 · 규격서 변경 이력
- 흐름 — vault `.claude/` 운영 커맨드(devlog · jira · weekly 등) 이관
