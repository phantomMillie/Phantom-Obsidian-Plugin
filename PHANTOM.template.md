# Phantom Obsidian — 이 PC 전역

- vault: `{{VAULT}}`
- 작업 폴더가 어디든, vault 안의 문서를 읽거나 쓰기 전에 `{{VAULT}}/AGENTS.md` 를 읽고 따른다 — 파일명 · 프론트매터 · 폴더 승인 규칙.
- 방법 스킬(Agent Skills): `flow-draft` → `flow-fill` → `qa-promote` (팬텀 플로우) · `policy-extract` (코드 정책 전수) · `glossary-add` (용어집). 해당 작업이면 스킬을 쓴다.
- 프레임워크 홈: `~/.millie-obsidian/`
- 프로젝트 Overview 는 완료 조건 · 마일스톤(날짜) · 완료일(`due`) 이 있어야 한다. 비어 있으면 그 프로젝트 작업·로그·회의 때 한 줄로 알리고 `/obsidian-project-scope <이름>` 을 제안한다. 점검: `<vault>/.scripts/project_lint.py`.
- 작업·마일스톤·결정이 끝나 완료를 보고하는 같은 턴에 `vault-record` 스킬로 vault 에 바로 기록한다(오늘 개발일지 한 줄 · 해당 마일스톤 체크). 기록 대상은 정확히 Projects/Areas/Resources/Archives/Store(임시로 밀린 것) 중 한 곳이고, 폴더·노트를 새로 만들거나 Archives·Store 로 옮기는 건 사용자에게 한 줄로 허락받은 뒤에만 한다(허락 전엔 `00. 미분류` 로그에 임시 기록). 진행 중·탐색은 기록하지 않는다. 날짜·완료 조건은 고치지 않고 제안만.
