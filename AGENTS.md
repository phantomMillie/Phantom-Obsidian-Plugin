# 이 레포를 설치해 달라는 요청을 받았을 때

**이것은 Obsidian 커뮤니티 플러그인이 아니다.** 이름에 Obsidian 이 들어가지만, Obsidian 앱의
`.obsidian/plugins/` 에 넣는 물건이 아니다. vault 를 고르는 질문도 하지 마라.

이것은 **PC 단위로 한 번 설치하는 AI 에이전트 프레임워크**다. 설치하면 Claude Code · Codex CLI ·
Gemini CLI 등 이 PC 의 모든 코딩 에이전트가, 어느 작업 폴더에서든 같은 전역 지침과 같은 스킬을 읽는다.
PC 당 설치는 하나이고, 연결되는 vault 도 `config.json` 의 `vault` 값 하나다.

## 설치 절차

먼저 이미 설치돼 있는지 본다. `~/.millie-obsidian` 이 있으면 새로 clone 하지 말고
`cd ~/.millie-obsidian && ./install.sh` 로 갱신만 한다.

그 다음 사용자에게 **딱 한 가지만** 묻는다 — 연결할 vault 가 이미 있는가, 새로 만드는가.

vault 를 새로 만드는 경우 — **위치를 묻지 마라.** 기본값은 프레임워크 홈 안 `~/.millie-obsidian/vault`
이고, `.gitignore` 에 걸려 있어 레포에 올라가지 않는다. 사용자가 먼저 다른 자리를 말할 때만
`./install.sh --init <폴더>` 로 폴더를 준다.

```bash
git clone https://github.com/phantomMillie/millie-obsidian-kit.git ~/.millie-obsidian
cd ~/.millie-obsidian
./install.sh --init
```

이미 vault 가 있는 경우:

```bash
git clone https://github.com/phantomMillie/millie-obsidian-kit.git ~/.millie-obsidian
cd ~/.millie-obsidian
cp config.example.json config.json      # "vault" 값을 기존 vault 절대 경로로 수정
./install.sh
```

`install.sh` 는 여러 번 돌려도 결과가 같다. `config.json` 을 고친 뒤에도 다시 돌리면 된다.

## install.sh 가 이 PC 에 건드리는 것

되돌릴 수 있는 변경만 하지만, 사용자 홈의 전역 설정 파일을 고친다는 점은 실행 전에 알려라.

| 경로 | 무엇 |
|---|---|
| `~/.millie-obsidian/` | 프레임워크 본체 (clone 위치. 다른 경로에 두지 않는다) |
| `~/.millie-obsidian/vault/` | vault 기본 자리. `.gitignore` 에 걸려 레포에 올라가지 않는다 |
| `~/.claude/CLAUDE.md` · `~/.gemini/GEMINI.md` · `~/.codex/AGENTS.md` | `<!-- millie-obsidian:start/end -->` 관리 블록 추가. 블록 밖은 건드리지 않는다 |
| `~/.agents/skills/*` | `skills/*` 로 가는 심볼릭 링크 |
| Claude Code 플러그인 | `millie-vault@millie-obsidian` 등록 |

해제는 `./install.sh --remove`. 관리 블록과 링크, 플러그인 등록만 지우고 레포 파일과 vault 는 남긴다.

## 설치 후 남는 일

Obsidian 쪽은 `install.sh` 가 Templater · Dataview 까지 받아서 켜고(`plugin/scripts/obsidian_setup.py`),
Obsidian 의 vault 목록에도 등록한다. 사용자에게 손으로 플러그인을 깔라고 안내하지 마라.
Obsidian 이 켜져 있었다면 껐다 켜야 vault 목록에 보인다는 것만 알려주면 된다.

내려받기가 실패했을 때만(네트워크 없음 등) `python3 plugin/scripts/obsidian_setup.py <vault>` 를 다시 돌린다.

나머지 구조 · 스킬 · 설정 키는 `README.md` 를 봐라.


## Codex 단독 설치와 권한

Claude Code나 macOS 바탕화면 앱 없이 Codex 연결만 필요하면, config.json의 기존 vault를 확인한 뒤 `python3 plugin/scripts/install_codex.py`를 실행한다. 이 경로는 vault 생성·데스크톱 앱 설치를 실행하지 않는다. 설치 후 Codex를 다시 시작하고 `/hooks`에서 새 훅을 사용자가 검토·신뢰해야 한다. 스킬 발견과 데이터 쓰기 권한은 별개다.

선택적인 `--configure-codex-permissions`는 Python 3.11 이상에서 이 프레임워크와 설정된 vault 경로만 추가한다. 승인 정책·네트워크·모델을 바꾸거나 전체 접근을 켜지 않는다. 이름 있는 권한 프로필이나 읽기 전용 모드를 임의로 대체하지 않는다. 사용자가 이미 허락한 작업을 스킬 자체의 별도 승인이 필요한 일로 다시 해석하지 않는다.

외부 스킬 호환 패치는 `plugin/scripts/install_skill_compat.py`를 사용한다. 기존 사용자 수정은 보존하고, Caveman Cloud 서비스·계정은 별도 의존성으로 보고한다. 로컬 config.json·vault·상태·API 키를 Git에 포함하지 않는다.
