# Phantom Obsidian Framework

Phantom Obsidian vault 작업 방식(팬텀 플로우 · 정책 추출 · 용어집)을 **이 PC의 모든 코딩 에이전트**가 쓰게 하는 프레임워크. 개인용.

> **Obsidian 커뮤니티 플러그인이 아니다.** 이름에 `Obsidian-Plugin` 이 들어가지만 `.obsidian/plugins/` 에 넣는 물건이 아니다.
> vault 마다 설치하는 게 아니라 **PC 당 한 번** `~/.phantom-obsidian` 에 설치하고, 연결되는 vault 는 `config.json` 의 `vault` 하나다.
> AI 에이전트에게 설치를 시킬 때는 [`AGENTS.md`](AGENTS.md) 를 먼저 읽게 하라.

```bash
git clone https://github.com/phantomMillie/Phantom-Obsidian-Plugin.git ~/.phantom-obsidian
cd ~/.phantom-obsidian
./install.sh --init                                # 새 vault 를 ~/.phantom-obsidian/vault 에 만들면서 설치
# 이미 vault 가 있으면: cp config.example.json config.json  →  "vault" 수정  →  ./install.sh
```

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
├── hooks/project_guard.py      프로젝트 필수 항목 리마인드 훅 (Claude Code)
├── scripts/vault_init.py       새 vault 생성 · 관리 파일 갱신
├── scripts/project_lint.py     프로젝트 필수 항목 점검 (원본)
├── vault-template/             vault 골격 (회사·개인 데이터 없음)
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
vault-record    작업·마일스톤이 끝난 턴에 vault 에 바로 기록 (개발일지 · 체크 · 영역 · 자료)
vault-init      새 vault 생성 (PARA 폴더 · AGENTS.md · 템플릿 · 점검 스크립트 · 대시보드)
```

## 확인 상태 (2026-10-08)

| 도구 | 전역 지침 | 스킬 |
|---|---|---|
| Claude Code | `/tmp` 새 세션에서 vault 경로 답함 ✅ | 플러그인 등록 ✅ |
| Codex CLI 0.153.4 | `/tmp` 새 세션에서 vault 경로 답함 ✅ | 5개 인식 ✅ |
| Gemini CLI 0.59.0 | 미확인 — 계정 티어가 Gemini CLI 지원 종료(Antigravity 이관 안내)라 모델 호출 불가 | `gemini skills list` 5개 ✅ |
| Copilot · Cursor · OpenCode | 미설치 | 문서상 `~/.agents/skills` 지원 |

## 설치

**vault 를 처음 만들 때 (새 컴퓨터 포함)** — 플러그인이 vault 골격을 가진다.

```bash
git clone https://github.com/phantomMillie/Phantom-Obsidian-Plugin.git ~/.phantom-obsidian
cd ~/.phantom-obsidian
./install.sh --init                                  # vault 생성 + config.json + PC 연결
```

vault 는 `~/.phantom-obsidian/vault` 에 생긴다 — 프레임워크 홈 안이고 `.gitignore` 에 걸려 있어 레포에 올라가지 않는다.
다른 자리에 두고 싶을 때만 `./install.sh --init <폴더>` 로 폴더를 준다.

또는 Claude Code 에서 "vault 만들어줘" → `vault-init` 스킬이 위치를 묻고 같은 일을 한다.
만들어지는 것: PARA 폴더 · `AGENTS.md` · 프로젝트 템플릿 9종 · `.scripts/project_lint.py` · `📓 Projects` 대시보드 · 팬텀 플로우 방법 문서 · 스킬이 쓰는 인박스/인덱스 스텁.
이미 있는 파일은 덮어쓰지 않는다.

**Templater · Dataview 는 `install.sh` 가 직접 설치한다** (`scripts/obsidian_setup.py`) — 최신 릴리스를 `<vault>/.obsidian/plugins/` 에 받고, 켜고,
템플릿 폴더 `Templetes` · Dataview JS 쿼리까지 맞추고, Obsidian 의 vault 목록에도 등록한다. Obsidian 을 껐다 켜면 목록에 vault 가 보이고 바로 쓸 수 있다.
네트워크가 없으면 내려받기만 건너뛰고 나머지는 끝난다. 통째로 건너뛰려면 `./install.sh --no-obsidian`.

**이미 vault 가 있을 때**

```bash
git clone https://github.com/phantomMillie/Phantom-Obsidian-Plugin.git ~/.phantom-obsidian
cd ~/.phantom-obsidian
cp config.example.json config.json      # "vault" 값 수정
./install.sh
```

vault 경로를 바꾸거나 템플릿을 고치면 `./install.sh` 다시. 해제는 `./install.sh --remove`.
프레임워크가 관리하는 vault 파일(점검 스크립트 · 커맨드)을 최신으로: `python3 scripts/vault_init.py <vault> --update` (`.bak` 백업, 나머지는 안 건드림).

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

## 프로젝트 필수 항목 가드

활성 프로젝트는 **완료 조건 · 마일스톤(날짜) · 완료일(`due`)** 이 있어야 한다. 비어 있으면 일이 오가는 동안 계속 리마인드한다. 점검 로직(`scripts/project_lint.py`)은 플러그인이 원본이고, vault-init 이 vault `.scripts/` 에 사본을 둔다. 훅은 플러그인 것을 직접 부르므로 vault 에 스크립트가 없어도 돈다.

| 경로 | 언제 |
|---|---|
| `hooks/project_guard.py` SessionStart | 세션 시작에 빈 프로젝트 요약 (최대 5개) |
| `hooks/project_guard.py` UserPromptSubmit | 프롬프트에 프로젝트 이름이 나오면 세션당 1번 상기 |
| vault `devlog_check.py` (Slack) | 오늘·최근 14일 일지가 있는 프로젝트가 비었으면 `추가 검토사항` 에 매일 |
| vault `📓 Projects` 대시보드 | `필수 항목` 열 |

vault 경로 · 스크립트가 없으면 훅은 조용히 아무것도 안 낸다. 채우기는 vault 의 `/obsidian-project-scope <이름>`.

## 실시간 기록 (배치 아님)

AI 가 작업·마일스톤·결정을 끝냈다고 보고하는 **같은 턴**에 `scripts/vault_record.py` 로 vault 에 바로 쓴다. SessionStart 훅이 이 규칙과 프로젝트 목록을 주입하고, `vault-record` 스킬이 절차를 갖는다.

| 하는 일 | 효과 |
|---|---|
| `devlog` | `<프로젝트> 개발일지/오늘.md` 의 한 일·결정·이슈·외부·로그에 한 줄 |
| `todo` | 오늘 `07. TODO` 에 할 일 — 중요도·마감·난이도 필수. `tools/todo-pile` 이 이 값으로 바탕화면에 쌓는다 |
| `tick` | 마일스톤·세부 목표·완료 조건 체크 → 대시보드 진행률에 즉시 반영 |
| `area` · `resource` | 영역 메모 · 자료 수집 노트에 한 줄 (이미 있는 것만) |

기록 대상은 **Projects / Areas / Resources / Archives / Store(임시로 밀린 것) 중 정확히 한 곳**이다 — PARAS.
기존 파일에 한 줄 추가·체크만 하고, `due`·날짜·완료 조건 문구는 안 고치고 제안만 한다. 같은 줄은 한 번만 남고, 비밀 문자열은 가려진다.

**폴더 생성·보관은 사용자 허락 후에만.** 기존에서 먼저 찾고(`match`), 정말 없을 때만 묻는다. 허락 전엔 `00. 미분류` 로그에 임시 기록하고, 허락되면 `new area|topic --name … --approved`, 프로젝트는 `new project --name … --due … --done … --milestone … --approved` (완료일·완료 조건·마일스톤이 없으면 거부 — 사용자가 나중에 정하겠다고 할 때만 `--scope-later`), 끝난 프로젝트는 `archive --project … --approved`, 임시로 밀린 프로젝트는 `shelve`(→ Store) · 다시 하면 `resume`. `--approved` 없이는 스크립트가 거부한다.
`para/collect.py`·`classify.py`(배치 수집)는 놓친 대화를 줍는 보조로 남는다.

## 다음 층 (예정)

- 가드 확장 — 파일명·프론트매터 린트 + PC 단위 실행(launchd 감시 / git pre-commit). 프로젝트 필수 항목 점검은 위에서 이미 동작
- 이력 — git 자동 커밋 · 규격서 변경 이력
- 흐름 — vault `.claude/` 운영 커맨드(devlog · jira · weekly 등) 이관
