#!/usr/bin/env python3
"""작업이 끝난 그 자리에서 vault 에 바로 기록한다 (배치 아님).

  vault_record.py devlog   --project P --section "한 일" --text "..."   오늘 개발일지에 한 줄
  vault_record.py tick     --project P --item "<항목 일부>"             마일스톤·세부 목표·완료 조건 체크
  vault_record.py area     --name N --text "..."                       2. Areas/🧵 N.md `## 🧠 메모`
  vault_record.py resource --topic T --text "..."                      3. Resources/T/📎 T 수집.md
  vault_record.py projects                                             기록할 수 있는 프로젝트 목록
  vault_record.py match    --name N                                    비슷한 기존 프로젝트·영역·자료 주제 (새로 만들기 전에 먼저)
  vault_record.py new project --name N --due D --done "조건" --milestone "D 내용" --approved
                                                                      새 프로젝트 (승인 + 완료일·완료 조건·마일스톤을 사용자에게 물어 받은 뒤에만)
  vault_record.py new area|topic --name N --approved                  새 영역·자료 주제 (사용자 승인 뒤에만)
  vault_record.py archive  --project P --approved                     끝난 프로젝트를 4. Archives 로 (사용자 승인 뒤에만)
  vault_record.py shelve   --project P --approved                     임시로 밀린 프로젝트를 5. Store 로 (사용자 승인 뒤에만)
  vault_record.py resume   --project P --approved                     Store 의 프로젝트를 1. Projects 로 되돌림 (사용자 승인 뒤에만)

규칙
- 기존 파일에 **한 줄 추가**만 한다. 지우거나 다시 쓰지 않는다. 날짜(due)·완료 조건 문구는 건드리지 않는다.
- 프로젝트·영역·주제는 이미 있는 것만 기록한다. 없으면 실패하고 비슷한 기존 이름을 보여 준다.
- **폴더·노트 생성과 보관(이동)은 `--approved` 가 있어야만** 한다. 이 플래그는 사용자가 방금 허락했다는 뜻이다 — 묻지 않고 붙이지 않는다.
- 같은 줄이 이미 있으면 건너뛴다 (같은 작업을 두 번 보고해도 한 번만 남는다).
- 비밀처럼 보이는 문자열은 가린다.
vault 위치: --vault · PHANTOM_VAULT · <플러그인>/config.json
"""
import argparse
import datetime
import difflib
import shutil
import json
import os
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SECTIONS = ["한 일", "결정", "이슈", "외부", "내일", "로그"]
PLACEHOLDER = re.compile(r"^-\s*(무엇을:|왜 \(.*\):|증상 / 원인 / 해결:|수치: before → after|TODO:|막힌 거 / 도움 필요:)?\s*$")
SECRET = [(re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)(\s*[:=]\s*)\S+"), r"\1\2***"),
          (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "sk-***"), (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "gh*_***")]


def die(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def clean(s):
    s = " ".join(s.split())
    for pat, rep in SECRET:
        s = pat.sub(rep, s)
    return s


def vault_and_paths(vault_arg):
    cfg = {}
    try:
        cfg = json.loads((pathlib.Path(os.environ.get("PHANTOM_HOME", ROOT)) / "config.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    v = vault_arg or os.environ.get("PHANTOM_VAULT") or cfg.get("vault")
    if not v or not pathlib.Path(v).expanduser().is_dir():
        die("vault 를 못 찾음 (--vault · PHANTOM_VAULT · config.json). `vault-init` 로 만들거나 config.json 을 고친다.")
    return pathlib.Path(v).expanduser(), cfg.get("paths", {})


def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, str(path))


def active_projects(vault, paths):
    root = vault / paths.get("projects", "1. Projects")
    return sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "📓"))) if root.is_dir() else []


def topics(vault, paths):
    root = vault / paths.get("resources", "3. Resources")
    return sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")) if root.is_dir() else []


def areas(vault, paths):
    root = vault / paths.get("areas", "2. Areas")
    return sorted(p.stem.replace("🧵 ", "", 1) for p in root.glob("🧵 *.md")) if root.is_dir() else []


def near(name, pool, n=3):
    low = name.lower()
    hit = [x for x in pool if low in x.lower() or x.lower() in low]
    return list(dict.fromkeys(hit + difflib.get_close_matches(name, pool, n=n, cutoff=0.4)))[:n]


def resolve_project(vault, paths, name):
    names = active_projects(vault, paths)
    if name in names:
        return name
    low = [n for n in names if n.lower() == name.lower() or re.sub(r"^\d+\.\s*", "", n) == name]
    if len(low) == 1:
        return low[0]
    store = vault / paths.get("store", "5. Store")
    if (store / name).is_dir():
        die("프로젝트 `%s` 는 5. Store(임시로 밀림)에 있다. 다시 시작하는 일이면 사용자에게 재개해도 되는지 묻고 `resume --project %s --approved`. "
            "아니면 기록하지 않는다." % (name, name))
    die("프로젝트 `%s` 없음. 비슷한 기존: %s / 전체: %s\n맞는 게 없으면: 사용자에게 새 프로젝트를 만들어도 되는지 한 줄로 묻는다 (승인 전엔 `00. 미분류` 에 임시 기록)."
        % (name, ", ".join(near(name, names)) or "-", ", ".join(names) or "(없음)"))


# ── devlog ─────────────────────────────────────────────────
DAILY = """---
title: Dev Log - {d}
date: {d}
project: {p}
tags: [Development, Daily]
---

[[1. Projects/{f}/📓 {p} Overview|🔗 {p}]]

## {d}

### 한 일
-

### 결정
- 무엇을:
- 왜 (대안 + 기각 사유):

### 이슈
- 증상 / 원인 / 해결:
- 수치: before → after

### 외부
-

### 내일
- TODO:
- 막힌 거 / 도움 필요:

---

## 로그
"""


def display(folder):
    """정렬용 숫자 접두사(`00. 미분류`)는 개발일지 이름·표기에서 뗀다."""
    return re.sub(r"^\d+\.\s*", "", folder)


def devlog_dir(vault, paths, project):
    inbox = paths.get("devlog_inbox", "3. Resources/03. 개발일지/📥 로그 인박스.md")
    return vault / pathlib.Path(inbox).parent / ("%s 개발일지" % display(project))


def add_to_section(text, section, line):
    """`### <section>` (로그는 `## 로그`) 에 한 줄 추가. 자리표시(`-`, `- 무엇을:` …)는 남기되 빈 `-` 한 줄은 대체."""
    head = "## 로그" if section == "로그" else "### " + section
    lines = text.split("\n")
    try:
        i = next(k for k, l in enumerate(lines) if l.strip() == head)
    except StopIteration:
        return None
    j = i + 1
    while j < len(lines) and not re.match(r"^(#{2,3} |---)", lines[j]):
        j += 1
    body = lines[i + 1:j]
    if any(b.strip() == line.strip() for b in body):
        return text                                              # 이미 있음
    last = max((k for k, b in enumerate(body) if b.strip()), default=-1)
    idx = [k for k, b in enumerate(body) if b.strip() == "-"]
    first_ph = next((k for k, b in enumerate(body) if PLACEHOLDER.match(b.strip())), None)
    if section != "로그" and idx:
        body[idx[0]] = line                                    # 빈 `-` 한 줄은 대체
    elif section != "로그" and first_ph is not None:
        body.insert(first_ph, line)                            # 자리표시 앞에
    else:
        body.insert(last + 1, line)                            # 마지막 실제 줄 바로 뒤 (빈 줄은 뒤로 밀림)
    out = "\n".join(lines[:i + 1] + body + lines[j:])
    return out if out.endswith("\n") else out + "\n"


def cmd_devlog(a):
    vault, paths = vault_and_paths(a.vault)
    project = resolve_project(vault, paths, a.project)
    if a.section not in SECTIONS:
        die("섹션은 %s 중 하나" % ", ".join(SECTIONS))
    now = datetime.datetime.now()
    d = devlog_dir(vault, paths, project)
    d.mkdir(parents=True, exist_ok=True)
    f = d / ("%s.md" % now.strftime("%Y-%m-%d"))
    text = f.read_text(encoding="utf-8") if f.exists() else DAILY.format(d=now.strftime("%Y-%m-%d"), p=display(project), f=project)
    t = clean(a.text)
    line = "- `%s` %s" % (now.strftime("%H:%M"), t) if a.section == "로그" else "- " + t
    new = add_to_section(text, a.section, line)
    if new is None:
        die("%s 에 `%s` 섹션이 없다 (형식이 다른 파일은 건드리지 않는다)" % (f.name, a.section))
    if new == text and f.exists():
        print("이미 있음 — 건너뜀: %s" % f.name)
        return
    atomic_write(f, new)
    print("기록 %s ▸ %s ▸ %s" % (project, f.name, a.section))


# ── tick ───────────────────────────────────────────────────
TICK_SECTIONS = ["🏁 마일스톤", "📋 세부 목표", "✅ 완료 조건"]


def cmd_tick(a):
    vault, paths = vault_and_paths(a.vault)
    project = resolve_project(vault, paths, a.project)
    ov = next((vault / paths.get("projects", "1. Projects") / project).glob("📓*Overview.md"), None)
    if not ov:
        die("%s 의 Overview 가 없다" % project)
    lines = ov.read_text(encoding="utf-8").split("\n")
    cur, hits = None, []
    for k, l in enumerate(lines):
        if l.startswith("## "):
            cur = next((s for s in TICK_SECTIONS if s in l), None)
        elif cur and re.match(r"^\s*- \[ \] ", l) and a.item.lower() in l.lower():
            hits.append((k, cur))
    if not hits:
        done = [l for l in lines if re.match(r"^\s*- \[[xX]\] ", l) and a.item.lower() in l.lower()]
        print("이미 완료됨 — 건너뜀" if done else "미완료 항목 중 `%s` 와 맞는 게 없다 (마일스톤·세부 목표·완료 조건)" % a.item)
        sys.exit(0 if done else 1)
    if len(hits) > 1:
        die("`%s` 가 %d개와 맞는다 — 더 구체적으로: %s" % (a.item, len(hits), " | ".join(lines[k].strip() for k, _ in hits)))
    k, sec = hits[0]
    lines[k] = lines[k].replace("- [ ]", "- [x]", 1)
    atomic_write(ov, "\n".join(lines))
    body = [l for l in lines if False]
    # 해당 섹션 진행 현황
    cur, tot, dn = None, 0, 0
    for l in lines:
        if l.startswith("## "):
            cur = next((s for s in TICK_SECTIONS if s in l), None)
        elif cur == sec and re.match(r"^\s*- \[[ xX]\] \S", l):
            tot += 1
            dn += bool(re.match(r"^\s*- \[[xX]\]", l))
    print("체크 %s ▸ %s: %s  (%s %d/%d)" % (project, sec, lines[k].strip(), sec, dn, tot))


# ── area / resource ────────────────────────────────────────
def append_under(path, heading, line, create_head=False):
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    try:
        i = next(k for k, l in enumerate(lines) if l.strip().startswith(heading))
    except StopIteration:
        if not create_head:
            die("%s 에 `%s` 섹션이 없다" % (path.name, heading))
        lines += ["", heading, ""]
        i = len(lines) - 2
    j = i + 1
    while j < len(lines) and not lines[j].startswith("## "):
        j += 1
    if any(l.strip() == line.strip() for l in lines[i + 1:j]):
        print("이미 있음 — 건너뜀: %s" % path.name)
        return False
    end = j
    while end > i + 1 and not lines[end - 1].strip():
        end -= 1
    lines.insert(end, line)
    atomic_write(path, "\n".join(lines))
    return True


def cmd_area(a):
    vault, paths = vault_and_paths(a.vault)
    areas = vault / paths.get("areas", "2. Areas")
    f = areas / ("🧵 %s.md" % a.name)
    if not f.exists():
        names = sorted(p.stem[2:] for p in areas.glob("🧵 *.md")) if areas.is_dir() else []
        die("영역 `%s` 없음. 비슷한 기존: %s / 전체: %s\n맞는 게 없으면: 사용자에게 새 영역을 만들어도 되는지 한 줄로 묻는다 (승인 전엔 `00. 미분류` 개발일지 로그에 임시 기록)."
            % (a.name, ", ".join(near(a.name, names)) or "-", ", ".join(names) or "(없음)"))
    line = "- %s %s" % (datetime.date.today().isoformat(), clean(a.text))
    if append_under(f, "## 🧠 메모", line):
        print("기록 Area ▸ %s ▸ 🧠 메모" % a.name)


def cmd_resource(a):
    vault, paths = vault_and_paths(a.vault)
    d = vault / paths.get("resources", "3. Resources") / a.topic
    if not d.is_dir():
        pool = topics(vault, paths)
        die("자료 주제 `%s` 없음. 비슷한 기존: %s / 전체: %s\n맞는 게 없으면: 사용자에게 새 주제 폴더를 만들어도 되는지 한 줄로 묻는다 (승인 전엔 `00. 미분류` 개발일지 로그에 임시 기록)."
            % (a.topic, ", ".join(near(a.topic, pool)) or "-", ", ".join(pool) or "(없음)"))
    f = d / ("📎 %s 수집.md" % a.topic)
    if not f.exists():
        atomic_write(f, "---\ntype: resource-collection\ntopic: %s\ncreated: %s\ntags: [resource/%s]\n---\n\n# 📎 %s 수집\n\n## 수집\n\n"
                     % (a.topic, datetime.date.today().isoformat(), a.topic.replace(" ", "-"), a.topic))
    line = "- %s %s" % (datetime.date.today().isoformat(), clean(a.text))
    if append_under(f, "## 수집", line, create_head=True):
        print("기록 Resource ▸ %s ▸ 수집" % a.topic)



# ── 생성 · 보관 (사용자 승인 필요) ──────────────────────────
def need_approval(a, what):
    if not a.approved:
        die("%s — 사용자 승인이 필요하다. 한 줄로 허락을 구한 뒤 승인되면 `--approved` 를 붙여 다시 호출한다." % what)


LIT = r"`((?:\\.|[^`\\])*)`"


def unlit(t, **v):
    t = t.replace("\\`", "`").replace("\\$", "$").replace("\\\\", "\\")
    for k, val in v.items():
        t = t.replace("${%s}" % k, val)
    return t


def template_text(vault, filename):
    f = vault / "Templetes" / filename
    if not f.exists():
        die("템플릿 %s 이 vault 에 없다" % filename)
    return f.read_text(encoding="utf-8")


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def scope_args(a):
    """새 프로젝트의 완료일·완료 조건·마일스톤. 사용자가 답한 값이어야 한다 — 없으면 만들지 않고 물어보게 한다."""
    if a.scope_later:
        return None
    miss = []
    if not a.due or not DATE_RE.match(a.due) or a.due.startswith("9999"):
        miss.append("--due YYYY-MM-DD (완료일)")
    if not (a.done or "").strip():
        miss.append('--done "<완료 조건 한 문장>"')
    ms = [m.strip() for m in (a.milestone or []) if m.strip()]
    if not ms or any(not DATE_RE.match(m.split(" ", 1)[0]) for m in ms):
        miss.append('--milestone "YYYY-MM-DD <내용>" (1개 이상, 날짜로 시작)')
    if miss:
        die("새 프로젝트는 만들면서 완료일 · 완료 조건 · 마일스톤을 같이 받는다. 빠진 것: %s\n"
            "→ 사용자에게 먼저 묻는다(말한 값만 쓴다, 지어내지 않는다). 사용자가 \"나중에\"라고 하면 `--scope-later` 로 비워 만들고 `/obsidian-project-scope` 를 제안한다." % ", ".join(miss))
    return a.due, a.done.strip(), ms


def fill_scope(ov, due, done, ms):
    """Overview 의 due · 완료 조건 · 마일스톤 빈 칸을 채운다. 칸을 못 찾으면 실패 (비어 있는 채로 조용히 만들지 않는다)."""
    ov, n = re.subn(r"^due:[ \t]*$", "due: " + due, ov, count=1, flags=re.M)
    if not n:
        die("Overview 에서 `due:` 칸을 못 찾았다 (템플릿 구조가 바뀜)")
    for head, lines in (("## ✅ 완료 조건", [done]), ("## 🏁 마일스톤", ms)):
        pat = re.compile(r"(%s\n(?:>.*\n)*)- \[ \][ \t]*\n" % re.escape(head))
        if not pat.search(ov):
            die("Overview 에서 `%s` 의 빈 항목을 못 찾았다 (템플릿 구조가 바뀜)" % head)
        ov = pat.sub(lambda m: m.group(1) + "".join("- [ ] %s\n" % l for l in lines), ov, count=1)
    return ov


def cmd_match(a):
    vault, paths = vault_and_paths(a.vault)
    for label, pool in (("프로젝트", active_projects(vault, paths)), ("영역", areas(vault, paths)), ("자료 주제", topics(vault, paths))):
        print("%s: %s" % (label, ", ".join(near(a.name, pool)) or "-"))


def cmd_new(a):
    vault, paths = vault_and_paths(a.vault)
    name = a.name.strip()
    if not name or "/" in name:
        die("이름이 비었거나 `/` 가 들어 있다")
    today = datetime.date.today().isoformat()
    if a.kind == "project":
        need_approval(a, "새 프로젝트 `%s`" % name)
        scope = scope_args(a)
        root = vault / paths.get("projects", "1. Projects")
        if (root / name).exists():
            die("프로젝트 `%s` 이미 있다" % name)
        t = template_text(vault, "00_프로젝트 템플릿.md")
        tag = "project/" + "-".join(name.split())
        files = {}
        for var, path in re.findall(r"tp\.file\.create_new\((\w+), `([^`]*)`\)", t):
            m = re.search(r"const %s = %s;" % (var, LIT), t)
            if m:
                files[unlit(path, title=name)] = unlit(m.group(1), title=name, tag=tag, created=today)
        ov = re.search(r"tR \+= %s;" % LIT, t)
        if not ov or len(files) < 4:
            die("프로젝트 템플릿 형식을 못 읽었다 (구조가 바뀜). Templater 로 직접 만든다.")
        ov_text = unlit(ov.group(1), title=name, tag=tag, created=today)
        if scope:
            ov_text = fill_scope(ov_text, *scope)
        files["1. Projects/%s/📓 %s Overview" % (name, name)] = ov_text
        made = []
        for rel, body in files.items():
            dst = vault / (rel + ".md")
            dst.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(dst, body)
            made.append(dst.name)
        if scope:
            print("프로젝트 생성 %s (%d개 파일). 완료일 %s · 완료 조건 1 · 마일스톤 %d 채움" % (name, len(made), scope[0], len(scope[2])))
        else:
            print("프로젝트 생성 %s (%d개 파일). --scope-later: 완료 조건·마일스톤·완료일 비어 있다 → /obsidian-project-scope %s" % (name, len(made), name))
    elif a.kind == "area":
        need_approval(a, "새 영역 `%s`" % name)
        root = vault / paths.get("areas", "2. Areas")
        f = root / ("🧵 %s.md" % name)
        if f.exists():
            die("영역 `%s` 이미 있다" % name)
        m = re.search(r"const content = %s;" % LIT, template_text(vault, "01_관심 템플릿.md"))
        if not m:
            die("영역 템플릿 형식을 못 읽었다")
        root.mkdir(parents=True, exist_ok=True)
        atomic_write(f, unlit(m.group(1), title=name, today=today))
        print("영역 생성 %s" % f.name)
    else:
        need_approval(a, "새 자료 주제 폴더 `%s`" % name)
        d = vault / paths.get("resources", "3. Resources") / name
        if d.exists():
            die("자료 주제 `%s` 이미 있다" % name)
        d.mkdir(parents=True)
        atomic_write(d / ("📎 %s 수집.md" % name), "---\ntype: resource-collection\ntopic: %s\ncreated: %s\ntags: [resource/%s]\n---\n\n# 📎 %s 수집\n\n## 수집\n\n"
                     % (name, today, "-".join(name.split()), name))
        print("자료 주제 생성 %s" % name)


def cmd_archive(a):
    vault, paths = vault_and_paths(a.vault)
    need_approval(a, "프로젝트 `%s` 보관(4. Archives 로 이동)" % a.project)
    proj_root = vault / paths.get("projects", "1. Projects")
    store_root = vault / paths.get("store", "5. Store")
    src = next((r / a.project for r in (proj_root, store_root) if (r / a.project).is_dir()), None)
    if src is None:
        die("프로젝트 `%s` 가 1. Projects · 5. Store 에 없다" % a.project)
    dst = vault / paths.get("archives", "4. Archives") / a.project
    if dst.exists():
        die("4. Archives/%s 이미 있다" % a.project)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    dev = devlog_dir(vault, paths, a.project)
    moved_dev = False
    if dev.is_dir():
        shutil.move(str(dev), str(dst / dev.name))             # 규약: 종료 시 개발일지도 폴더째 같이
        moved_dev = True
    ov = next(dst.glob("📓*Overview.md"), None)
    if ov:
        set_frontmatter(ov, "done", None)
    n = relink(dst, a.project, src.parent.relative_to(vault).as_posix(), paths.get("archives", "4. Archives"))
    print("보관 %s → %s%s (status: done, 자기 폴더 링크 %d개 문서 갱신). 다른 문서에서 옛 경로 `[[%s/%s/...]]` 로 거는 링크는 직접 확인 필요"
          % (a.project, dst.relative_to(vault), " (+개발일지)" if moved_dev else "", n, src.parent.relative_to(vault).as_posix(), a.project))


def relink(folder, name, old_root, new_root):
    """옮긴 폴더 안 문서의 자기 폴더 링크(`[[<옛>/<이름>/...`)만 새 위치로. 다른 곳으로 가는 링크는 안 건드린다."""
    old, new = "[[%s/%s/" % (old_root, name), "[[%s/%s/" % (new_root, name)
    n = 0
    for f in folder.rglob("*.md"):
        t = f.read_text(encoding="utf-8")
        if old in t:
            atomic_write(f, t.replace(old, new))
            n += 1
    return n


def set_frontmatter(ov, status, tags):
    t = ov.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", t, re.S)
    if not m:
        return
    fm = m.group(1)
    fm = re.sub(r"^status:.*$", "status: " + status, fm, count=1, flags=re.M) if re.search(r"^status:", fm, re.M) else re.sub(r"^(tags:)", "status: %s\n\\1" % status, fm, count=1, flags=re.M)
    if tags is not None:
        fm = re.sub(r"^tags:.*$", "tags: [%s]" % tags, fm, count=1, flags=re.M)
    atomic_write(ov, "---\n" + fm + "\n---\n" + t[m.end():])


def move_project(a, src_key, dst_key, status, tags_fn, what):
    vault, paths = vault_and_paths(a.vault)
    need_approval(a, what)
    roots = {"projects": paths.get("projects", "1. Projects"), "store": paths.get("store", "5. Store"),
             "archives": paths.get("archives", "4. Archives")}
    src, dst = vault / roots[src_key] / a.project, vault / roots[dst_key] / a.project
    if not src.is_dir():
        die("`%s/%s` 가 없다" % (roots[src_key], a.project))
    if dst.exists():
        die("`%s/%s` 이미 있다" % (roots[dst_key], a.project))
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    ov = next(dst.glob("📓*Overview.md"), None)
    if ov:
        set_frontmatter(ov, status, tags_fn(a.project))
    n = relink(dst, a.project, roots[src_key], roots[dst_key])
    return vault, paths, dst, n


def cmd_shelve(a):
    vault, paths, dst, n = move_project(a, "projects", "store", "paused", lambda p: "project/paused", "프로젝트 `%s` 보류(5. Store 로 이동)" % a.project)
    print("보류 %s → %s (status: paused, 자기 폴더 링크 %d개 문서 갱신). 개발일지는 그대로 둔다. 다시 하게 되면 resume" % (a.project, dst.relative_to(vault), n))


def cmd_resume(a):
    vault, paths, dst, n = move_project(a, "store", "projects", "active", lambda p: "project/" + "-".join(p.split()), "프로젝트 `%s` 재개(1. Projects 로 이동)" % a.project)
    print("재개 %s → %s (status: active, 링크 %d개 문서 갱신). 완료 조건·마일스톤·완료일이 비었으면 /obsidian-project-scope %s" % (a.project, dst.relative_to(vault), n, a.project))


def cmd_projects(a):
    vault, paths = vault_and_paths(a.vault)
    print("\n".join(active_projects(vault, paths)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--vault", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("devlog"); s.add_argument("--project", required=True)
    s.add_argument("--section", default="한 일"); s.add_argument("--text", required=True); s.set_defaults(fn=cmd_devlog)
    s = sub.add_parser("tick"); s.add_argument("--project", required=True); s.add_argument("--item", required=True); s.set_defaults(fn=cmd_tick)
    s = sub.add_parser("area"); s.add_argument("--name", required=True); s.add_argument("--text", required=True); s.set_defaults(fn=cmd_area)
    s = sub.add_parser("resource"); s.add_argument("--topic", required=True); s.add_argument("--text", required=True); s.set_defaults(fn=cmd_resource)
    sub.add_parser("projects").set_defaults(fn=cmd_projects)
    s = sub.add_parser("match"); s.add_argument("--name", required=True); s.set_defaults(fn=cmd_match)
    s = sub.add_parser("new"); s.add_argument("kind", choices=["project", "area", "topic"]); s.add_argument("--name", required=True)
    s.add_argument("--due"); s.add_argument("--done"); s.add_argument("--milestone", action="append")
    s.add_argument("--scope-later", action="store_true", help="사용자가 나중에 정하겠다고 한 경우만")
    s.add_argument("--approved", action="store_true"); s.set_defaults(fn=cmd_new)
    s = sub.add_parser("archive"); s.add_argument("--project", required=True); s.add_argument("--approved", action="store_true"); s.set_defaults(fn=cmd_archive)
    for nm, fn in (("shelve", cmd_shelve), ("resume", cmd_resume)):
        s = sub.add_parser(nm); s.add_argument("--project", required=True); s.add_argument("--approved", action="store_true"); s.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
