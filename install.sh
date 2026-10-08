#!/usr/bin/env bash
# 이 PC에 프레임워크를 연결한다. 세션 · 작업 폴더와 무관하게 모든 AI 도구가 같은 지침 · 스킬을 읽게 한다.
# 여러 번 돌려도 같은 결과. config.json 을 바꾼 뒤에도 다시 돌린다.
#
#   ./install.sh            연결 / 갱신
#   ./install.sh --remove   연결 해제 (이 레포 파일은 그대로)
#
# 하는 일
#   1. config.json 의 vault 경로로 PHANTOM.md(전역 지침) 생성
#   2. skills/ → ~/.agents/skills 링크          (Codex · Gemini CLI · Copilot · Cursor · OpenCode)
#   3. 전역 지침 파일에 관리 블록                (홈 폴더가 있는 도구만)
#        ~/.claude/CLAUDE.md   PHANTOM.md import
#        ~/.gemini/GEMINI.md   PHANTOM.md import
#        ~/.codex/AGENTS.md    PHANTOM.md 내용 (Codex 는 import 없음)
#   4. Claude Code 플러그인 등록 (스킬)
#   관리 블록 밖 내용은 건드리지 않는다.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
REMOVE=0; [ "${1:-}" = "--remove" ] && REMOVE=1

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
elif f.exists():
    f.unlink()
print(("갱신 " if src else "제거 ") + str(f))
EOF
}

if [ "$REMOVE" = 1 ]; then
  for s in "$REPO"/skills/*/; do l="$HOME/.agents/skills/$(basename "$s")"; [ -L "$l" ] && rm "$l" && echo "제거 $l"; done
  [ -d "$HOME/.claude" ] && block "$HOME/.claude/CLAUDE.md" ""
  [ -d "$HOME/.gemini" ] && block "$HOME/.gemini/GEMINI.md" ""
  [ -d "$HOME/.codex"  ] && block "$HOME/.codex/AGENTS.md" ""
  if command -v claude >/dev/null; then
    claude plugin uninstall phantom-vault@phantom-obsidian >/dev/null 2>&1 || true
    claude plugin marketplace remove phantom-obsidian >/dev/null 2>&1 || true
    echo "제거 Claude Code 플러그인"
  fi
  exit 0
fi

# 1. 전역 지침 생성
[ -f "$REPO/config.json" ] || { echo "config.json 없음 — cp config.example.json config.json 후 vault 경로 수정" >&2; exit 1; }
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
for s in "$REPO"/skills/*/; do
  l="$HOME/.agents/skills/$(basename "$s")"
  if [ -e "$l" ] && [ ! -L "$l" ]; then echo "건너뜀 $l — 링크 아닌 파일이 이미 있음" >&2; continue; fi
  ln -sfn "${s%/}" "$l" && echo "링크 $l"
done

# 3. 전역 지침 관리 블록
IMPORT="$(mktemp)"; printf '@%s\n' "$REPO/PHANTOM.md" > "$IMPORT"
[ -d "$HOME/.claude" ] && block "$HOME/.claude/CLAUDE.md" "$IMPORT"
[ -d "$HOME/.gemini" ] && block "$HOME/.gemini/GEMINI.md" "$IMPORT"
[ -d "$HOME/.codex"  ] && block "$HOME/.codex/AGENTS.md" "$REPO/PHANTOM.md"
rm -f "$IMPORT"

# 4. Claude Code 플러그인 (로컬 폴더를 직접 읽으므로 수정 즉시 반영)
if command -v claude >/dev/null; then
  claude plugin marketplace add "$REPO" >/dev/null 2>&1 || true
  claude plugin install phantom-vault@phantom-obsidian >/dev/null 2>&1 || true
  echo "등록 Claude Code 플러그인 phantom-vault@phantom-obsidian"
fi
