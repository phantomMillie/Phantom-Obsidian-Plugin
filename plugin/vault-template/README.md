# Millie Vault

이 vault 는 `millie-vault` 플러그인의 `vault-init` 으로 만들었다. 규칙은 [[AGENTS]] 에 있다.

## 처음 한 번

1. Obsidian 에서 이 폴더를 vault 로 연다
2. 커뮤니티 플러그인 설치: **Templater** (템플릿 폴더 `Templetes`) · **Dataview** (JavaScript 쿼리 켜기)
3. 새 프로젝트: Templater 로 `00_프로젝트 템플릿` 실행 → `1. Projects/<이름>/` 에 5개 파일이 생긴다

## 프로젝트 필수 항목

완료 조건 · 마일스톤(날짜) · 완료일(`due`). 점검: `python3 .scripts/project_lint.py`. 채우기: `/obsidian-project-scope <이름>`.
