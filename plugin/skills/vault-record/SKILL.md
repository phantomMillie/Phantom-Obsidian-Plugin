---
name: vault-record
description: 작업·마일스톤·결정이 끝난 그 턴에 vault 에 바로 기록한다 — 오늘 개발일지 한 줄, 마일스톤/세부 목표 체크(진행률 반영), 영역 메모, 자료 수집. 배치 아님. "개발일지에 남겨줘", "마일스톤 체크", "vault 에 기록", "/vault-record" 요청에 쓰고, 작업 완료를 보고하는 같은 턴에 스스로도 호출한다.
---

# 끝난 자리에서 기록

```bash
MILLIE_PLUGIN="${CLAUDE_PLUGIN_ROOT:-$HOME/.millie-obsidian/plugin}"
record_vault() { python3 "$MILLIE_PLUGIN/scripts/vault_record.py" "$@"; }
record_vault projects                                                     # 기록 가능한 프로젝트
record_vault devlog --project <이름> --section "한 일" --text "..."        # 섹션: 한 일 · 결정 · 이슈 · 외부 · 로그
record_vault todo   --project <이름> --text "..." --importance 상|중|하 --due YYYY-MM-DD --effort ⚡|🔸|🧱   # 할 일. 셋 다 사용자에게 받은 값만 (없으면 거부 → 먼저 묻는다)
record_vault issue  --project <이름> --section "프로젝트 이슈" --text "..."  # 안 풀린 문제 → 🚨 <이름> 이슈.md (프로젝트 · 정책 · 일정 이슈)
record_vault tick   --project <이름> --item "<항목 일부>"                  # 마일스톤 · 세부 목표 · 완료 조건 체크
record_vault area   --name <영역> --text "..."                            # 2. Areas/🧵 <영역>.md › 🧠 메모
record_vault resource --topic <주제> --text "..."                         # 3. Resources/<주제>/📎 <주제> 수집.md
record_vault match  --name <이름>                                        # 새로 만들기 전에: 비슷한 기존 프로젝트 · 영역 · 주제
record_vault new project|area|topic --name <이름> --approved             # 새 폴더 · 노트 (사용자 허락 뒤에만)
record_vault archive --project <이름> --approved                         # 끝난 프로젝트 → 4. Archives (사용자 허락 뒤에만)
record_vault shelve  --project <이름> --approved                         # 임시로 밀린 프로젝트 → 5. Store (사용자 허락 뒤에만)
record_vault resume  --project <이름> --approved                         # Store → 1. Projects 로 되돌림 (사용자 허락 뒤에만)
```

## 5분류(PARAS) — 기록할 가치가 있는 프롬프트는 정확히 한 곳

| 곳 | 기준 | 하는 일 |
|---|---|---|
| **Projects** | 끝이 있는 일 (완료 조건 · 기한) | `devlog` + 해당 항목이면 `tick` |
| **Areas** | 끝이 없는 지속 책임 | `area` 메모 |
| **Resources** | 나중에 찾아볼 참고 지식 · 자료 · 정책 | `resource` 수집 |
| **Archives** | 끝난 것 | `archive` (프로젝트가 완전히 끝났을 때만) |
| **Store** | 임시로 밀린 것 (나중에 다시 할 일) | `shelve` (Projects → Store) · 다시 하면 `resume`. Store 프로젝트에는 일지를 쓰지 않는다 |

판정 순서: 끝이 있나 → Projects / 지속 책임 → Areas / 참고용 → Resources / 끝났나 → Archives / 지금은 못 하고 미룬다 → Store. 질문 · 잡담 · 탐색은 기록하지 않는다.

## 폴더 생성 = 사용자 허락 (매번 만들 수 없다)

1. **기존에서 먼저 찾는다**: `record_vault match --name <이름>`. 비슷한 게 있으면 그쪽에 기록한다.
2. 정말 없을 때만 **한 줄로 묻는다**: `새 <프로젝트|영역|자료 주제> \`<이름>\` 만들까요? (이유 한 줄)`. **프로젝트면 완료일 · 완료 조건 · 마일스톤(날짜)도 같은 질문에서 같이 묻는다.**
3. 답을 기다리는 동안: `00. 미분류` 개발일지 로그에 `[분류 대기: 영역 보안] ...` 로 임시 기록 (잃어버리지 않기 위해).
4. 허락되면 → 그 곳에 기록. 영역·주제는 `record_vault new area|topic --name <이름> --approved`, 프로젝트는 `record_vault new project --name <이름> --due <YYYY-MM-DD> --done "<완료 조건>" --milestone "<YYYY-MM-DD 내용>" --approved` (`--milestone` 은 여러 번 가능). 거절되면 미분류에 두고 **같은 이름을 다시 묻지 않는다**.
5. `--approved` 는 사용자가 방금 허락했을 때만 붙인다. 보관(`archive`) · 보류(`shelve`) · 재개(`resume`)도 이동이라 같은 규칙. 이동 뒤 `[[옛 경로]]` 링크는 직접 확인해서 알린다.

새 프로젝트는 완료일 · 완료 조건 · 마일스톤 없이는 스크립트가 만들지 않는다(거부 메시지가 빠진 항목을 알려 준다). 값은 사용자가 말한 것만 쓰고 지어내지 않는다. 사용자가 "나중에"라고 할 때만 `--scope-later` 로 비워 만들고 `/obsidian-project-scope <이름>` 을 제안한다.

## 언제

- **끝났을 때만.** 기능 하나 · 마일스톤 하나 · 결정 · 이슈 해결을 사용자에게 보고하는 **같은 턴**. 다음 턴으로 미루면 사라진다. 묻지 않는다.
- 질문 · 탐색 · 진행 중 단계 · 실패한 시도는 기록하지 않는다.
- 한 작업에 `devlog` 한 줄 + 해당 항목이 있으면 `tick`. 대시보드 진행률은 체크박스에서 나오므로 `tick` 이 곧 진척 반영이다.

## 무엇을

- `한 일`: 결과 한 줄 (무엇이 되었나). `결정`: 무엇을 + 왜(기각한 대안). `이슈`: 증상 / 원인 / 해결.
- 사실만. 추측 · 다짐 · 사과 · 비밀(토큰 · 키) 금지. 비밀처럼 보이면 스크립트가 가린다.
- 프로젝트가 불명이면 `00. 미분류`. 새 프로젝트 · 영역 · 주제 폴더는 허락 없이 만들지 않는다 (`--approved` 없으면 스크립트가 거부한다).

## 하지 않는 것

- `due` · 마일스톤 날짜 · 완료 조건 문구를 고치지 않는다. 일정이 밀렸으면 **제안만** 하고 사용자 답을 기다린다.
- 항목이 둘 이상 맞으면(`tick` 이 거부) 더 구체적인 문구로 다시 호출한다. 임의로 고르지 않는다.
- 같은 줄은 한 번만 남는다 (중복 호출 안전).

기록 후 한 줄로 보고한다: `기록: <프로젝트> ▸ <섹션>` (+ `체크: <항목> (n/m)`).

## Codex 실행 조건

현재 세션이 설정된 vault에 쓸 수 있어야 기록이 완료된다. 스킬 읽기·사용자 대화상 허락만으로 샌드박스 권한이 바뀌지는 않는다. 쓰기가 거부되면 승인된 작업 폴더에 대기 내용을 보존하고 vault 반영은 미완료라고 보고한다.
