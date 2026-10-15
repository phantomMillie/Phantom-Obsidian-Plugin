---
name: vault-init
description: 새 Phantom vault(PARA 폴더 · AGENTS.md · 프로젝트 템플릿 · 점검 스크립트 · 대시보드)를 만든다. "vault 만들어줘", "옵시디언 폴더 새로 세팅", "팬텀 vault 초기화", "새 컴퓨터에 vault 세팅", "vault 갱신" 요청에 사용.
---

# vault 만들기

플러그인이 vault 골격을 갖고 있다. 다른 컴퓨터에서도 플러그인만 설치하면 같은 vault 가 나온다.

## 순서

1. **위치는 묻지 않는다.** 기본값은 프레임워크 홈 안 `~/.phantom-obsidian/vault` — `.gitignore` 에 걸려 레포에 올라가지 않는다.
   사용자가 먼저 다른 자리를 말하거나 이미 vault 가 있을 때만 그 경로를 쓴다(기존 파일은 안 덮는다).
2. 만든다:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/vault_init.py" "${CLAUDE_PLUGIN_ROOT}/vault" --set-default
   ```
3. PC 에 연결한다(전역 지침 · 스킬 링크):
   ```bash
   cd ~/.phantom-obsidian && ./install.sh
   ```
4. 사용자에게 한 번만 안내: Obsidian 에서 폴더 열기 → **Templater**(템플릿 폴더 `Templetes`) · **Dataview**(JS 쿼리 켜기) 설치.

## 규칙

- 이미 있는 파일은 절대 덮어쓰지 않는다. 지우지 않는다.
- `--update` 는 프레임워크 관리 파일(`.scripts/project_lint.py`, `.claude/commands/*`)만 새 버전으로 바꾼다 (`.bak` 백업).
  AGENTS.md · 템플릿 · 사용자 문서는 안 건드린다 — 바뀐 점은 차이만 보고한다.
- 회사·개인 데이터는 골격에 없다. 사용자가 쓴 문서를 템플릿으로 되돌려 넣지 않는다.
- 끝나면 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project_lint.py" --vault "<경로>"` 로 점검이 도는지 확인하고, 결과(만든 수 / 건너뛴 수)를 한 줄로 보고한다.
