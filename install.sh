#!/usr/bin/env bash
# 이 PC에 프레임워크를 연결한다. 세션 · 작업 폴더와 무관하게 모든 AI 도구가 같은 지침 · 스킬을 읽게 한다.
# 여러 번 돌려도 같은 결과. config.json 을 바꾼 뒤에도 다시 돌린다.
#
#   ./install.sh            연결 / 갱신
#   ./install.sh --init          vault 를 레포 안 ./vault 에 새로 만들고(plugin/scripts/vault_init.py) 연결까지
#   ./install.sh --init <폴더>   vault 를 다른 자리에 만들고 싶을 때만 폴더를 준다
#   ./install.sh --remove   연결 해제 (이 레포 파일은 그대로)
#   --no-obsidian           Obsidian 플러그인 설치 · vault 등록을 건너뛴다
#   --no-todo-pile          바탕화면 TODO 앱(macOS) 설치를 건너뛴다
#
# 하는 일
#   1. config.json 의 vault 경로로 PHANTOM.md(전역 지침) 생성
#   2. skills/ → ~/.agents/skills 링크          (Codex · Gemini CLI · Copilot · Cursor · OpenCode)
#   3. 전역 지침 파일에 관리 블록                (홈 폴더가 있는 도구만)
#        ~/.claude/CLAUDE.md   PHANTOM.md import
#        ~/.gemini/GEMINI.md   PHANTOM.md import
#        ~/.codex/AGENTS.md    PHANTOM.md 내용 (Codex 는 import 없음)
#   4. Claude Code 플러그인 등록 (스킬)
#   5. vault 에 Templater · Dataview 설치 + Obsidian vault 목록에 등록 (plugin/scripts/obsidian_setup.py)
#   6. 바탕화면 TODO 앱 빌드 + 로그인 시 자동 실행 (plugin/scripts/bootstrap.py — 플러그인 훅도 같은 걸 한다)
#   관리 블록 밖 내용은 건드리지 않는다.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
REMOVE=0; [ "${1:-}" = "--remove" ] && REMOVE=1

if [ "${1:-}" = "--init" ]; then
  PHANTOM_HOME="$REPO" python3 "$REPO/plugin/scripts/vault_init.py" "${2:-$REPO/vault}" --set-default
fi

# 관리 블록 쓰기/지우기: block <파일> <내용파일|""(지우기)>
block() {
  python3 - "$1" "$2" <<'EOF'
import pathlib, re, sys
f, src = pathlib.Path(sys.argv[1]), sys.argv[2]
S, E = "<!-- phantom-obsidian:start -->", "<!-- phantom-obsidian:end -->"
txt = f.read_text(encoding="utf-8") if f.exists() else ""
txt = re.sub(r"\n?" + re.escape(S) + r".*?" + re.escape(E) + r"\n?", "\n", txt, flags=re.S).strip("\n")
if src:
    body = pathlib.Path(src).read_text(encoding="utf-8").strip("\n")
    txt = (txt + "\n\n" if txt else "") + f"{S}\n{body}\n{E}"
if txt:
    f.write_text(txt + "\n", encoding="utf-8")
    # 블록만 넣고 뺀다. 사용자가 쓴 나머지 내용은 그대로 남는다.
    print(("갱신 " if src else "블록 제거 ") + str(f))
elif f.exists():
    # 블록을 빼고 나니 빈 파일 — 우리가 만든 파일이었다는 뜻이다.
    f.unlink()
    print("삭제 " + str(f))
else:
    print("없음 " + str(f))
EOF
}

if [ "$REMOVE" = 1 ]; then
  for s in "$REPO"/plugin/skills/*/; do l="$HOME/.agents/skills/$(basename "$s")"; [ -L "$l" ] && rm "$l" && echo "제거 $l"; done
  [ -d "$HOME/.claude" ] && block "$HOME/.claude/CLAUDE.md" ""
  [ -d "$HOME/.gemini" ] && block "$HOME/.gemini/GEMINI.md" ""
  [ -d "$HOME/.codex"  ] && block "$HOME/.codex/AGENTS.md" ""
  if command -v claude >/dev/null; then
    claude plugin uninstall phantom-vault@phantom-obsidian >/dev/null 2>&1 || true
    claude plugin marketplace remove phantom-obsidian >/dev/null 2>&1 || true
    echo "제거 Claude Code 플러그인"
  fi
  # Obsidian vault 목록에서 뺀다 — 안 빼면 없어진 폴더를 가리키는 항목이 남는다.
  # vault 폴더와 그 안의 문서는 지우지 않는다.
  if [ -f "$REPO/config.json" ]; then
    V="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("vault",""))' "$REPO/config.json")"
    [ -n "$V" ] && python3 "$REPO/plugin/scripts/obsidian_setup.py" "$V" --unregister
  fi
  exit 0
fi

# 1. 전역 지침 생성
[ -f "$REPO/config.json" ] || { echo "config.json 없음 — ./install.sh --init <새 vault 폴더> 로 vault 를 만들거나, cp config.example.json config.json 후 기존 vault 경로 수정" >&2; exit 1; }
VAULT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["vault"])' "$REPO/config.json")"
[ -d "$VAULT" ] || { echo "vault 폴더 없음: $VAULT" >&2; exit 1; }
python3 - "$REPO/PHANTOM.template.md" "$REPO/PHANTOM.md" "$VAULT" <<'EOF'
import pathlib, sys
t = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
pathlib.Path(sys.argv[2]).write_text(t.replace("{{VAULT}}", sys.argv[3]), encoding="utf-8")
EOF
echo "생성 $REPO/PHANTOM.md"

# 2. 스킬 링크
mkdir -p "$HOME/.agents/skills"
for s in "$REPO"/plugin/skills/*/; do
  l="$HOME/.agents/skills/$(basename "$s")"
  if [ -e "$l" ] && [ ! -L "$l" ]; then echo "건너뜀 $l — 링크 아닌 파일이 이미 있음" >&2; continue; fi
  ln -sfn "${s%/}" "$l" && echo "링크 $l"
done

# 3. 전역 지침 관리 블록
IMPORT="$(mktemp)"; printf '@%s\n' "$REPO/PHANTOM.md" > "$IMPORT"
# 홈 폴더가 아직 없어도 CLI 가 깔려 있으면 만들어서 쓴다 — 처음 설치하는 PC 에서는
# ~/.claude 같은 폴더가 그 도구를 한 번 돌린 뒤에야 생기기 때문.
want() { [ -d "$HOME/$1" ] || command -v "$2" >/dev/null; }
want .claude claude && { mkdir -p "$HOME/.claude"; block "$HOME/.claude/CLAUDE.md" "$IMPORT"; }
want .gemini gemini && { mkdir -p "$HOME/.gemini"; block "$HOME/.gemini/GEMINI.md" "$IMPORT"; }
want .codex  codex  && { mkdir -p "$HOME/.codex";  block "$HOME/.codex/AGENTS.md" "$REPO/PHANTOM.md"; }
rm -f "$IMPORT"

# 4. Claude Code 플러그인 — Claude 는 plugin/ 을 ~/.claude/plugins/cache/ 로 복사해서 돌린다.
#    그래서 스킬·훅을 고친 뒤에는 이 스크립트를 다시 돌려야 반영된다.
#    source 를 ./plugin 으로 좁혀 둔 덕에 config.json · vault 는 복사되지 않는다.
if command -v claude >/dev/null; then
  # 이미 등록돼 있으면 marketplace add 가 marketplace.json 을 다시 읽지 않는다.
  # 먼저 떼고 붙여야 source 변경과 새 버전이 반영된다.
  claude plugin marketplace remove phantom-obsidian >/dev/null 2>&1 || true
  claude plugin marketplace add "$REPO" >/dev/null 2>&1 || true
  claude plugin install phantom-vault@phantom-obsidian >/dev/null 2>&1 || true
  echo "등록 Claude Code 플러그인 phantom-vault@phantom-obsidian"
fi

# 5. Obsidian 쪽 준비 — Templater · Dataview 설치 · 설정 · vault 등록
#    네트워크가 없으면 내려받기만 실패하고 나머지는 끝난다. --no-obsidian 으로 통째로 건너뛴다.
case " $* " in
  *" --no-obsidian "*) echo "건너뜀 Obsidian 준비 (--no-obsidian)" ;;
  *) python3 "$REPO/plugin/scripts/obsidian_setup.py" "$VAULT" || true ;;
esac

# 6. 바탕화면 TODO 앱 · Obsidian 설정 — 플러그인 훅이 세션 시작 때 똑같이 한다. 여기서는 바로 끝까지 돌린다.
if [ -n "${PHANTOM_NO_TODO_PILE:-}" ] || case " $* " in *" --no-todo-pile "*) true;; *) false;; esac; then
  PHANTOM_NO_TODO_PILE=1 PHANTOM_HOME="$REPO" python3 "$REPO/plugin/scripts/bootstrap.py" || true
else
  PHANTOM_HOME="$REPO" python3 "$REPO/plugin/scripts/bootstrap.py" || true
fi
