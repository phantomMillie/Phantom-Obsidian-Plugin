#!/usr/bin/env python3
"""새 vault 를 만든다 — PARA 폴더 · AGENTS.md · 템플릿 · 점검 스크립트 · 대시보드.

  python3 vault_init.py <만들 폴더> [--set-default] [--update]

  --set-default   <플러그인 폴더>/config.json 의 vault 를 이 폴더로 (없으면 새로 만든다)
  --update        프레임워크가 관리하는 파일(.scripts/project_lint.py · .claude/commands/*)만 최신으로 덮어쓴다

원칙: 이미 있는 파일은 절대 덮어쓰지 않는다 (--update 의 관리 파일만 예외, 덮기 전 .bak). 지우지 않는다.
회사·개인 데이터는 들어 있지 않다. 표준 라이브러리만 쓴다.
"""
import json
import os
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "vault-template"
HOME = pathlib.Path(os.environ.get("PHANTOM_HOME", ROOT))          # config.json 은 플러그인 폴더에 둔다 (install.sh 와 같은 곳)
MANAGED = [".scripts/project_lint.py", ".claude/commands/obsidian-project-scope.md"]

CONFIG_PATHS = {
    "projects": "1. Projects", "areas": "2. Areas", "resources": "3. Resources",
    "archives": "4. Archives", "store": "5. Store",
    "method_doc": "3. Resources/00. Reference/00. 기초자료/팬텀 플로우.md",
    "meetings": "3. Resources/01. Meeting", "flow_output": "3. Resources/99. QA",
    "glossary": "3. Resources/02. 용어집", "glossary_index": "3. Resources/02. 용어집/📖 용어집.md",
    "policy_index": "3. Resources/00. Reference/02. 정책/🗂️ 정책 인덱스.md",
    "devlog_inbox": "3. Resources/03. 개발일지/📥 로그 인박스.md",
    "issue_inbox": "3. Resources/03. 개발일지/📥 이슈 인박스.md",
    "para_inbox": "📥 PARA 인박스.md", "para_history": "📤 PARA 이동 히스토리.md",
}


def sources():
    """(vault 안 상대경로, 원본 파일) — 템플릿 트리 + 플러그인이 원본인 점검 스크립트."""
    for f in sorted(TEMPLATE.rglob("*")):
        if f.is_file():
            yield f.relative_to(TEMPLATE).as_posix(), f
    yield ".scripts/project_lint.py", ROOT / "scripts" / "project_lint.py"


def init(target, update=False):
    target.mkdir(parents=True, exist_ok=True)
    made, kept, updated = [], [], []
    for rel, src in sources():
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(src, dst)
            made.append(rel)
        elif update and rel in MANAGED and dst.read_bytes() != src.read_bytes():
            shutil.copy2(dst, str(dst) + ".bak")
            shutil.copy2(src, dst)
            updated.append(rel)
        else:
            kept.append(rel)
    return made, kept, updated


def write_config(target, force):
    cfg_file = HOME / "config.json"
    HOME.mkdir(parents=True, exist_ok=True)
    cfg = {}
    if cfg_file.exists():
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        if cfg.get("vault") and cfg["vault"] != str(target) and not force:
            return "config 유지 (이미 다른 vault: %s). 바꾸려면 --set-default" % cfg["vault"]
    cfg["vault"] = str(target)
    cfg.setdefault("paths", CONFIG_PATHS)
    cfg.setdefault("classify", {"fallback_project": "미분류", "resource_skip": ["02. 용어집", "03. 개발일지"]})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return "config 기록: %s" % cfg_file


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    target = pathlib.Path(args[0]).expanduser().resolve()
    made, kept, updated = init(target, "--update" in argv)
    print("vault: %s" % target)
    print("만듦 %d / 이미 있어 건너뜀 %d / 갱신 %d" % (len(made), len(kept), len(updated)))
    for r in updated:
        print("  갱신(.bak 백업) %s" % r)
    print(write_config(target, "--set-default" in argv))
    print("다음: ./install.sh — PC 연결 · Templater · Dataview 설치 · Obsidian vault 등록까지 한다.")


if __name__ == "__main__":
    main(sys.argv[1:])
