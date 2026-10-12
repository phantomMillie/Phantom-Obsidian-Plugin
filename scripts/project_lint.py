#!/usr/bin/env python3
# 프로젝트 필수 항목 점검 — 완료 조건 · 마일스톤 · 완료일(due) 이 비어 있는 활성 프로젝트를 찾는다.
#
#   python3 .scripts/project_lint.py                 # 전체 표
#   python3 .scripts/project_lint.py --project 결제   # 한 프로젝트
#   python3 .scripts/project_lint.py --brief         # 리마인드용 한 줄씩 (비었을 때만 출력)
#   python3 .scripts/project_lint.py --json          # 훅·배치용
#   python3 project_lint.py --vault <경로>           # vault 밖(플러그인)에서 실행할 때
#
# 읽기만 한다. 고치는 건 `/obsidian-project-scope <프로젝트>` (질문으로 채움).
# 활성 프로젝트(1. Projects/<이름>/📓 <이름> Overview.md) 만 본다. 5. Store · 4. Archives 는 대상 아님.
#
# 필수 3종 (AGENTS.md "프로젝트 필수 항목")
#   ✅ 완료 조건   `## ✅ 완료 조건` 에 비어 있지 않은 항목 1개 이상
#   🏁 마일스톤    `## 🏁 마일스톤` 에 날짜(YYYY-MM-DD) 가 붙은 항목 1개 이상
#   📆 완료일      frontmatter `due: YYYY-MM-DD` (9999 · 빈칸 = 미설정)

import datetime
import json
import os
import pathlib
import re
import sys

def resolve_vault(argv):
    """vault 안(.scripts/)에서 돌면 그 vault. 플러그인에서 돌면 --vault · PHANTOM_VAULT · <플러그인 폴더>/config.json."""
    here = pathlib.Path(__file__).resolve().parent.parent
    if "--vault" in argv:
        return pathlib.Path(argv[argv.index("--vault") + 1]).expanduser()
    if os.environ.get("PHANTOM_VAULT"):
        return pathlib.Path(os.environ["PHANTOM_VAULT"]).expanduser()
    if (here / "1. Projects").exists():
        return here
    home = pathlib.Path(os.environ.get("PHANTOM_HOME", here))
    try:
        return pathlib.Path(json.loads((home / "config.json").read_text(encoding="utf-8"))["vault"]).expanduser()
    except Exception:
        return here


VAULT = resolve_vault(sys.argv[1:])
PROJ_DIR = VAULT / "1. Projects"
SYSTEM_BUCKETS = {"00. 미분류", "01. Daily"}     # 프로젝트가 아니라 분류용 칸 — 점검 제외
DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
PLACEHOLDERS = {"", "완료 조건", "마일스톤", "이 프로젝트의 최종 목표는 무엇인가?"}


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    fm = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def section(text, heading):
    """`## <heading...>` 부터 다음 `## ` 직전까지."""
    m = re.search(r"^##\s*" + re.escape(heading) + r"[^\n]*\n(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    return m.group(1) if m else None


def items(body):
    """비어 있지 않은 항목만. 인용(`>`)·구분선·빈 체크박스·자리표시 제외."""
    out = []
    for line in (body or "").splitlines():
        s = line.strip()
        if not s or s.startswith((">", "---", "<!--")):
            continue
        s = re.sub(r"^[-*]\s*(\[[ xX]\]\s*)?", "", s).replace("**", "").strip()
        s = re.sub(r"^#+\s*", "", s)
        if s in PLACEHOLDERS or s.startswith("⏸"):
            continue
        out.append(s)
    return out


def valid_date(s):
    m = DATE.search(s or "")
    if not m or m.group(1) == "9999":
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def check(overview, today):
    text = overview.read_text(encoding="utf-8", errors="ignore")
    fm = frontmatter(text)
    missing, notes = [], []

    if not items(section(text, "✅ 완료 조건")):
        missing.append("완료 조건")

    ms = section(text, "🏁 마일스톤")
    dated = [i for i in items(ms) if valid_date(i)]
    if not dated:
        missing.append("마일스톤(날짜)")

    due = valid_date(fm.get("due", ""))
    if not due:
        missing.append("완료일(due)")
    elif due < today and fm.get("status", "active") == "active":
        notes.append("완료일 초과 %s" % due.isoformat())

    for i in items(ms):
        d = valid_date(i)
        line = next((l for l in (ms or "").splitlines() if i[:20] in l), "")
        if d and d < today and "[ ]" in line:
            notes.append("마일스톤 지연 %s" % d.isoformat())
            break
    return {"missing": missing, "notes": notes, "due": due.isoformat() if due else "",
            "status": fm.get("status", "")}


def scan(only=None, today=None):
    today = today or datetime.date.today()
    rows = []
    if not PROJ_DIR.exists():
        return rows
    for d in sorted(p for p in PROJ_DIR.iterdir() if p.is_dir() and not p.name.startswith((".", "📓"))):
        if d.name in SYSTEM_BUCKETS or (only and d.name != only):
            continue
        ov = next(d.glob("📓*Overview.md"), None)
        if ov is None:
            rows.append({"project": d.name, "missing": ["Overview 파일"], "notes": [], "due": "", "status": "",
                         "path": str(d)})
            continue
        r = check(ov, today)
        r.update(project=d.name, path=str(ov))
        rows.append(r)
    return rows


def main(argv):
    only = argv[argv.index("--project") + 1] if "--project" in argv else None
    rows = scan(only)
    bad = [r for r in rows if r["missing"] or r["notes"]]
    if "--json" in argv:
        print(json.dumps(rows, ensure_ascii=False))
        return
    if "--brief" in argv:
        for r in bad:
            parts = ["없음: " + ", ".join(r["missing"])] if r["missing"] else []
            parts += r["notes"]
            print("- %s — %s" % (r["project"], " / ".join(parts)))
        return
    print("%-22s %-8s %s" % ("프로젝트", "완료일", "상태"))
    for r in rows:
        state = "OK" if not (r["missing"] or r["notes"]) else " / ".join(
            (["없음: " + ", ".join(r["missing"])] if r["missing"] else []) + r["notes"])
        print("%-22s %-10s %s" % (r["project"], r["due"] or "-", state))
    print("\n%d개 중 %d개 보완 필요. 채우기: /obsidian-project-scope <프로젝트>" % (len(rows), len(bad)))


if __name__ == "__main__":
    main(sys.argv[1:])
