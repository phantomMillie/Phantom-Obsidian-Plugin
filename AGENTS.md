# 이 레포를 설치해 달라는 요청을 받았을 때

**이것은 Obsidian 커뮤니티 플러그인이 아니다.** 이름에 `Obsidian-Plugin` 이 들어가지만, Obsidian 앱의
`.obsidian/plugins/` 에 넣는 물건이 아니다. vault 를 고르는 질문도 하지 마라.

이것은 **PC 단위로 한 번 설치하는 AI 에이전트 프레임워크**다. 설치하면 Claude Code · Codex CLI ·
Gemini CLI 등 이 PC 의 모든 코딩 에이전트가, 어느 작업 폴더에서든 같은 전역 지침과 같은 스킬을 읽는다.
PC 당 설치는 하나이고, 연결되는 vault 도 `config.json` 의 `vault` 값 하나다.

## 설치 절차

먼저 이미 설치돼 있는지 본다. `~/.phantom-obsidian` 이 있으면 새로 clone 하지 말고
`cd ~/.phantom-obsidian && ./install.sh` 로 갱신만 한다.

그 다음 사용자에게 **딱 한 가지만** 묻는다 — 연결할 vault 가 이미 있는가, 새로 만드는가.

vault 를 새로 만드는 경우:

```bash
git clone https://github.com/phantomMillie/Phantom-Obsidian-Plugin.git ~/.phantom-obsidian
cd ~/.phantom-obsidian
./install.sh --init <만들 vault 폴더>
```

이미 vault 가 있는 경우:

```bash
git clone https://github.com/phantomMillie/Phantom-Obsidian-Plugin.git ~/.phantom-obsidian
cd ~/.phantom-obsidian
cp config.example.json config.json      # "vault" 값을 기존 vault 절대 경로로 수정
./install.sh
```

`install.sh` 는 여러 번 돌려도 결과가 같다. `config.json` 을 고친 뒤에도 다시 돌리면 된다.

## install.sh 가 이 PC 에 건드리는 것

되돌릴 수 있는 변경만 하지만, 사용자 홈의 전역 설정 파일을 고친다는 점은 실행 전에 알려라.

| 경로 | 무엇 |
|---|---|
| `~/.phantom-obsidian/` | 프레임워크 본체 (clone 위치. 다른 경로에 두지 않는다) |
| `~/.claude/CLAUDE.md` · `~/.gemini/GEMINI.md` · `~/.codex/AGENTS.md` | `<!-- phantom-obsidian:start/end -->` 관리 블록 추가. 블록 밖은 건드리지 않는다 |
| `~/.agents/skills/*` | `skills/*` 로 가는 심볼릭 링크 |
| Claude Code 플러그인 | `phantom-vault@phantom-obsidian` 등록 |

해제는 `./install.sh --remove`. 관리 블록과 링크, 플러그인 등록만 지우고 레포 파일과 vault 는 남긴다.

## 설치 후 남는 일

Obsidian 에서 vault 폴더를 열고 **Templater**(템플릿 폴더 `Templetes`) 와 **Dataview**(JS 쿼리 켜기)
를 설치하라고 안내한다. 이 둘은 vault 템플릿과 대시보드가 쓰는 실제 Obsidian 플러그인이다.

나머지 구조 · 스킬 · 설정 키는 `README.md` 를 봐라.
