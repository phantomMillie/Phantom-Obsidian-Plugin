#!/usr/bin/env python3
# PARA 분류기 — vault 루트 `📥 PARA 인박스.md` 의 사건을 PARA 위치로 보낸다.
# 규격: PARA 프레임워크 규격서 (config `paths.spec_doc`). vault 경로 · 이름은 전부 config.json — 아래 `<키>` 는 config `paths` 키
#
#   python3 classify.py --dry-run     판단만 출력. 아무 파일도 안 건드림
#   python3 classify.py               분류 + 📤 이동 히스토리 + Slack
#     --no-llm     규칙 + 폴백만
#     --no-slack   Slack 안 보냄
#
# 분류 3단 (개발일지 분배와 같은 구조). LLM 이 죽어도 인박스는 빈다.
#   ① 규칙  사건의 피쳐가 프로젝트 이름과 같으면 그 프로젝트.
#           키워드 규칙(<keyword_rules>)은 LLM 에 후보로만 준다 — 긴 요약에선 짧은 키워드(예: `tc`)가 엉뚱한 프로젝트에 걸린다.
#           LLM 을 못 쓰면 폴백 + 후보는 히스토리에만.
#   ② LLM  나머지 위치 + 프로젝트 사건의 개발일지 섹션 · 이슈 · 할 일. 외부 LLM 조건(Q15)은 llm.py.
#   ③ 폴백 미분류.
#
# 보내는 곳
#   프로젝트 (Q5 · Q9 · Q10) — 개발일지 · 이슈 · TODO 파일은 기존 분배 배치가 쓴다. 여기선 그 인박스에 명시 태그로 넘긴다.
#     개발일지 (항상)       <devlog_inbox>  `[프로젝트|섹션] 원문`
#     이슈 (문제가 남으면)   <issue_inbox>   `[프로젝트|이슈 섹션] 원문`
#     할 일 (남은 일)        <devlog_inbox> `[프로젝트|내일] 원문` → 분배 배치가 할 일 목록으로
#   Areas (Q6 · Q11)    <areas>/🧵 <영역>.md 의 `## 🧠 메모`.
#                       영역 노트가 없으면 PARA 인박스에 승인 체크박스를 달고 남긴다. 체크하면 다음 실행 때 만들고 옮긴다.
#   Resources           <resources>/<주제 폴더>/📎 <주제> 수집.md
#   판정 불가           <devlog_inbox> `[<classify.fallback_project>|로그]`
# 결과는 vault 루트 `📤 PARA 이동 히스토리.md` + Slack(Q13, 개발일지 영수증과 같은 웹훅).
# 이동 히스토리에 남은 para-id 는 다시 처리하지 않는다 (중간에 죽어도 중복 기록 없음).
# 교정을 규칙으로 올리는 것(Q14)은 아직 없음.
import argparse, datetime, json, os, pathlib, re, subprocess, sys, tempfile, time, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config, llm  # noqa: E402

HOME = pathlib.Path.home()
ROOT = pathlib.Path(__file__).resolve().parent.parent           # ~/.millie-obsidian
LOG_FILE = ROOT / "state" / "classify.log"

DEVLOG_SECTIONS = ["한 일", "결정", "이슈", "외부", "로그"]       # `내일` 은 할 일로 따로
ISSUE_SECTIONS = ["프로젝트 이슈", "정책 이슈", "일정 이슈"]


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")




def one_line(text, limit=200):
    s = re.sub(r"\s+", " ", (text or "").replace("`", "'")).strip()
    return s if len(s) <= limit else s[:limit - 1] + "…"


# ── vault 구조 ────────────────────────────────────────────────────

def projects(vault):
    """{표시명: 폴더}. 개발일지 분배의 project_folders() 와 같은 규칙 (`00. 미분류` → `미분류`)."""
    out = {}
    d = config.vpath("projects")
    for p in sorted(d.iterdir()) if d.exists() else []:
        if p.is_dir() and not p.name.startswith((".", "📓")):
            out[re.sub(r"^\d+\.\s*", "", p.name)] = p
    return out


def areas(vault):
    d = config.vpath("areas")
    return {p.stem.replace("🧵", "", 1).strip(): p for p in sorted(d.glob("🧵*.md"))} if d.exists() else {}


SYSTEM_DIRS = ("meetings", "glossary", "todo", "devlog_inbox", "issue_inbox", "policy_index", "glossary_index")


def resource_topics(vault):
    """자료 주제 폴더. 회의 · 용어집 · 개발일지 · TODO 처럼 다른 기능이 쓰는 폴더는 뺀다."""
    d = config.vpath("resources")
    out = {}
    paths = config.load()["paths"]
    res = pathlib.PurePosixPath(paths.get("resources", "")).parts
    system = {"07. TODO", "01. Meeting", "03. 개발일지", "02. 용어집"}
    for k in SYSTEM_DIRS:
        rel = pathlib.PurePosixPath(paths.get(k) or "").parts
        if len(rel) > len(res) and rel[:len(res)] == res:
            system.add(rel[len(res)])
    for p in sorted(d.iterdir()) if d.exists() else []:
        if p.is_dir() and not p.name.startswith(".") and p.name not in set(config.classify_opt("resource_skip") or []) | system:
            out[re.sub(r"^\d+\.\s*", "", p.name)] = p
    return out


def keyword_rules(vault):
    try:
        return json.loads(config.vpath("keyword_rules").read_text(encoding="utf-8")).get("projects", {})
    except (OSError, AttributeError, json.JSONDecodeError):
        return {}


# ── PARA 인박스 ───────────────────────────────────────────────────
WIKILINK = re.compile(r"\[\[[^|\]]*\|([^\]]+)\]\]")          # [[경로|이름]] → 이름 (Slack 용)
RECORD = re.compile(r"^## (?P<title>.+?)\n(?P<body>.*?)^<!-- para-id: (?P<id>\w+) -->[ \t]*$", re.S | re.M)
APPROVE = re.compile(r"^- \[([ xX])\] (🧵|📎) (.+?) (영역|자료 주제) 만들기")


def parse_inbox(text):
    first = RECORD.search(text)
    header = text[:first.start()].rstrip("\n") if first else text.rstrip("\n")
    records = []
    for m in RECORD.finditer(text):
        fields, approve = {}, None
        for ln in m.group("body").splitlines():
            ck = APPROVE.match(ln)
            if ck:
                approve = (ck.group(1).lower() == "x", ck.group(3).strip(), "area" if ck.group(2) == "🧵" else "resource")
                continue
            kv = re.match(r"^- ([^:]+):\s*(.*)$", ln)
            if kv:
                fields[kv.group(1).strip()] = kv.group(2).strip()
        records.append({"id": m.group("id"), "title": m.group("title").strip(), "fields": fields,
                        "approve": approve, "block": m.group(0)})
    return header, records


def with_approval(block, area):
    """승인 대기 줄을 붙인 블록. 이미 붙어 있으면 그대로."""
    if "영역 만들기" in block:
        return block
    head, tail = block.rsplit("<!-- para-id:", 1)
    return (head + f"- 대기: 새 영역 「{area}」 — 승인하면 만들고 옮긴다\n"
            f"- [ ] 🧵 {area} 영역 만들기 (체크하면 다음 분류 때 생성)\n<!-- para-id:" + tail)


# ── 판정 ──────────────────────────────────────────────────────────
RESULT_SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "kind": {"type": "string", "enum": ["project", "area", "resource", "unknown"]},
            "target": {"type": "string"},
            "new_area": {"type": "boolean"},
            "devlog_section": {"type": "string", "enum": DEVLOG_SECTIONS},
            "devlog_line": {"type": "string"},
            "issue_section": {"type": "string", "enum": ISSUE_SECTIONS + ["없음"]},
            "issue_line": {"type": "string"},
            "todos": {"type": "array", "items": {"type": "string"}},
            "note_line": {"type": "string"},
        },
        "required": ["id", "kind", "target", "new_area", "devlog_section", "devlog_line",
                     "issue_section", "issue_line", "todos", "note_line"],
        "additionalProperties": False,
    }}},
    "required": ["results"],
    "additionalProperties": False,
}

PROMPT = """너는 개발자 vault 의 PARA 분류기다. 아래 사건들을 각각 어디에 둘지 정한다.

위치 기준:
- project: 기한이 정해진 주제 = 아래 "진행 중 프로젝트" 중 하나. target = 프로젝트 이름 그대로
- area: 기한 없이 꾸준히 봐야 할 관리 영역. target = 기존 영역 이름. 맞는 게 없으면 새 영역 이름(짧은 명사)을 짓고 new_area=true
- resource: 프로젝트 · 영역이 아니라 나중에 참고할 자료. target = "자료 주제 폴더" 이름 그대로
- unknown: 확신할 수 없으면. 억지로 배정하지 마라
"규칙 후보"는 키워드로 걸린 프로젝트다. 참고만 하고, 사건 내용과 안 맞으면 무시한다.

project 일 때:
- devlog_section: 한 일(실제 작업) / 결정(정한 것) / 이슈(버그 · 막힘 · 원인 · 해결) / 외부(다른 팀 · 외부 요청) / 로그
- devlog_line: 개발일지에 들어갈 한 줄. 무엇을 했고 어떻게 끝났나. 120자 이내
- issue_section · issue_line: 해결 안 된 문제나 막힘이 남았을 때만 (프로젝트 이슈 / 정책 이슈 / 일정 이슈). 없으면 "없음" · ""
- todos: 미해결 중 앞으로 할 일인 것만, 한 줄씩. 없으면 []
area · resource 일 때: note_line = 그 노트에 남길 한 줄 (120자 이내). 그 외 필드는 기본값("로그", "", "없음", [])
project 가 아니면 devlog_line · issue_line · todos 는 비운다.
사건에 없는 내용을 지어내지 마라. 모든 사건에 결과 하나씩, id 그대로. JSON {{"results": [...]}} 하나만 출력하라.

진행 중 프로젝트: {projects}
영역: {areas}
자료 주제 폴더: {topics}

사건:
{records}"""


def rule_feature(rec, projs):
    feat = rec["fields"].get("피쳐", "").strip().lower()
    return next((p for p in projs if feat and feat not in ("—", "-") and feat == p.lower()), None)


def rule_keyword(rec, projs, rules):
    text = " ".join([rec["title"], rec["fields"].get("요약", ""), rec["fields"].get("피쳐", "")]).lower()
    return next((p for p, keys in rules.items() if p in projs and any(k.lower() in text for k in keys)), None)


def render_records(recs, hints):
    out = []
    for r in recs:
        f = r["fields"]
        parts = [f"피쳐: {f.get('피쳐', '—')}", f"종료: {f.get('종료', '—')}", f"요약: {f.get('요약', '—')}"]
        for k in ("해결", "미해결"):
            if f.get(k):
                parts.append(f"{k}: {f[k]}")
        if hints.get(r["id"]):
            parts.append(f"규칙 후보: {hints[r['id']]}")
        out.append(f"[{r['id']}] {r['title']}\n  " + " | ".join(parts))
    return "\n".join(out)


def plain_project(rec, proj, how):
    """LLM 없이 프로젝트로 보낼 때 — 개발일지 `한 일` 한 줄. 남은 건 줄 끝에 붙인다."""
    f = rec["fields"]
    line = f"{rec['title']} — {f.get('요약', '')}"
    if f.get("미해결"):
        line += f" (남음: {f['미해결']})"
    return {"id": rec["id"], "kind": "project", "target": proj, "how": how, "devlog_section": "한 일",
            "devlog_line": line, "issue_section": "없음", "issue_line": "", "todos": [], "note_line": "", "new_area": False}


def decide(recs, projs, area_map, topics, rules, use_llm):
    """[(rec, verdict)], llm_source, llm_error."""
    verdicts, todo, hints = {}, [], {}
    for r in recs:
        p = rule_feature(r, projs)
        if p:
            verdicts[r["id"]] = dict(plain_project(r, p, "규칙"), how="규칙")
        todo.append(r)                                  # 규칙으로 정해져도 섹션 · 이슈 · 할 일은 LLM 이 정한다
        kw = rule_keyword(r, projs, rules)
        if kw:
            hints[r["id"]] = kw
    source, error = "off", None
    if use_llm and todo:
        prompt = PROMPT.format(projects=", ".join(projs) or "없음", areas=", ".join(area_map) or "없음",
                               topics=", ".join(topics) or "없음", records=render_records(todo, hints))
        try:
            data, source = llm.call(prompt, RESULT_SCHEMA)
        except RuntimeError as e:
            error = str(e)
            log(f"LLM 실패: {e}")
        else:
            for v in data.get("results", []):
                if not v.get("kind"):                   # kind 를 빼먹었으면 target 으로 짐작한다
                    t = v.get("target", "")
                    v["kind"] = "project" if t in projs else ("resource" if t in topics else ("area" if t and v.get("note_line") else "unknown"))
                rid = v.get("id")
                if rid not in {r["id"] for r in todo}:
                    continue
                fixed = verdicts.get(rid)
                if fixed:                               # 피쳐 = 프로젝트 이름이면 위치는 규칙대로, 내용만 LLM
                    if v.get("kind") == "project" and v.get("target") == fixed["target"]:
                        verdicts[rid] = dict(v, how="규칙+LLM")
                    continue
                if v.get("kind") == "project" and v.get("target") not in projs:
                    continue
                if v.get("kind") == "resource" and v.get("target") not in topics:
                    continue
                if v.get("kind") == "area" and not v.get("target", "").strip():
                    continue
                if v.get("kind") in ("project", "area", "resource"):
                    verdicts[rid] = dict(v, how="LLM")
    out = []
    for r in recs:
        how = "폴백" + (f"(키워드 후보 {hints[r['id']]})" if hints.get(r["id"]) else "")
        out.append((r, verdicts.get(r["id"]) or plain_project(r, config.classify_opt("fallback_project"), how)))
    return out, source, error


# ── 쓰기 ──────────────────────────────────────────────────────────

def inbox_line(now, proj, section, text):
    return f"- `{now:%Y-%m-%d %H:%M}` [{proj}|{section}] {one_line(text)}"


def append_lines(path, lines):
    if not lines:
        return
    if not path.exists():
        raise RuntimeError(f"인박스 없음: {path}")
    t = path.read_text(encoding="utf-8").rstrip("\n")
    path.write_text(t + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


AREA_TEMPLATE = """---
type: area
created: {today}
tags: [area]
---

**카테고리**: #area
**생성일**: {today}

---

## 🎯 관리 목적
- [ ] 이 영역(Area)을 관리하는 이유는 무엇인가?

---

## 🔄 점검 항목 (Checkpoints)
- [ ] 최근 이 영역에서 점검해야 할 건?
- [ ] 개선해야 할 점은?
- [ ] 유지되고 있는 좋은 습관은?

---

## 🔗 관련 프로젝트
-

---

## 📚 참고 리소스
- [[{resources}/]]

---

## 🧠 메모
"""

RESOURCE_TEMPLATE = """---
type: para-collected
created: {today}
tags: [para, resource]
---

# 📎 {topic} 수집
> PARA 분류기가 AI 대화에서 이 주제로 분류한 사건. 원본은 vault 루트 `📤 PARA 이동 히스토리`.

"""


def add_note_line(path, bullet, heading="## 🧠 메모"):
    t = path.read_text(encoding="utf-8")
    if heading in t:
        i = t.index(heading) + len(heading)
        nxt = t.find("\n## ", i)
        body_end = len(t) if nxt == -1 else nxt
        sec = t[i:body_end].rstrip("\n")
        t = t[:i] + sec + "\n" + bullet + "\n" + ("\n" + t[body_end:].lstrip("\n") if nxt != -1 else "")
    else:
        t = t.rstrip("\n") + f"\n\n{heading}\n{bullet}\n"
    path.write_text(t, encoding="utf-8")


def history_header(today):
    return f"""---
type: para-history
created: {today}
tags: [para, history]
---

# 📤 PARA 이동 히스토리
> PARA 분류기가 사건을 어디로 보냈는지. 틀린 곳은 직접 옮기면 된다.
> 프로젝트로 간 줄은 개발일지 · 이슈 인박스를 거쳐 다음 분배 때 각 파일로 들어간다.
"""


def link_project(vault, projs, name):
    d = projs.get(name)
    return f"[[{d.relative_to(vault)}/📓 {name} Overview|{name}]]" if d else name


def send_slack(text):
    try:
        wf = config.local("slack_webhook")
        url = wf.read_text().strip() if wf and wf.exists() else ""
    except OSError:
        url = ""
    if not url:
        return "웹훅 없음"
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        return "전송"
    except Exception as e:
        return f"실패: {e}"



# ── AI 정리 (para-sort 스킬) ──────────────────────────────────────
# 판단은 사용자가 쓰고 있는 그 AI 가 한다 — 키 · 별도 LLM 호출 없음. 스크립트는 목록을 보여 주고(--pending)
# AI 가 낸 판정을 검사해 파일에 쓴다(--apply). 쓰기는 전부 vault_record.py 를 거친다(중복 건너뜀 · 승인 규칙).
LOCK = ROOT / "state" / "para-sort.lock"
LOCK_TTL = 30 * 60
RECORD_PY = ROOT / "plugin" / "scripts" / "vault_record.py"
ACTIONS = {"record", "skip", "defer"}
EFFORTS = ["⚡", "🔸", "🧱"]


def lock_age():
    try:
        return time.time() - json.loads(LOCK.read_text(encoding="utf-8")).get("at", 0)
    except (OSError, json.JSONDecodeError):
        return None


def claim(force=False):
    age = lock_age()
    if age is not None and age < LOCK_TTL and not force:
        return False, int(age // 60)
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(json.dumps({"at": time.time(), "pid": os.getpid()}), encoding="utf-8")
    return True, 0


def release():
    try:
        LOCK.unlink()
    except OSError:
        pass


def folder_map(projs):
    """코드 폴더 → 프로젝트 (바탕화면 TODO 의 코드 폴더 + 대화 폴더 학습)."""
    out = {}
    for f, pick in ((ROOT / "state" / "todo-pile.json", lambda d: {v: k for k, v in (d.get("dirs") or {}).items()}),
                    (ROOT / "state" / "session-projects.json", lambda d: d.get("dirs") or {})):
        try:
            out.update(pick(json.loads(f.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    return {k: v for k, v in out.items() if v in projs}


def convo_key(r):
    m = re.search(r"`([^`]+)`", r["fields"].get("기록", ""))
    return m.group(1) if m else r["id"]


def pending_records():
    inbox = config.vpath("para_inbox")
    if not inbox.exists():
        return []
    _, recs = parse_inbox(inbox.read_text(encoding="utf-8"))
    hist = config.vpath("para_history")
    done = set(re.findall(r"para-id: (\w+)", hist.read_text(encoding="utf-8"))) if hist.exists() else set()
    return [r for r in recs if r["id"] not in done]


def cmd_pending(a):
    vault = config.vault()
    recs = pending_records()
    if not recs:
        print("PARA 정리 대기 없음")
        return 0
    if a.claim:
        ok, mins = claim(a.force)
        if not ok:
            print(f"다른 대화가 정리 중 ({mins}분 전 시작) — 이번엔 건너뛴다")
            return 3
    projs, area_map, topics = projects(vault), areas(vault), resource_topics(vault)
    fmap = folder_map(projs)
    groups = {}
    for r in recs:
        groups.setdefault(convo_key(r), []).append(r)
    out = [f"# PARA 정리 대기 {len(recs)}건 (대화 {len(groups)}개) · 오늘 {datetime.date.today()}", "",
           "프로젝트: " + (", ".join(p for p in projs if p != config.classify_opt("fallback_project")) or "(없음)")
           + f" · 맞는 곳 없는 업무: {config.classify_opt('fallback_project')}",
           "영역: " + (", ".join(area_map) or "(없음)"),
           "자료 주제: " + (", ".join(topics) or "(없음)"),
           "코드 폴더 → 프로젝트: " + ("; ".join(f"{k} → {v}" for k, v in sorted(fmap.items())) or "(없음)"), ""]
    keys = ("도구", "폴더", "대화 프로젝트", "종료", "요약", "해결", "미해결", "대화", "이미 기록", "보류", "대기")
    for n, (key, rs) in enumerate(groups.items(), 1):
        out.append(f"## 대화 {n} — {rs[0]['fields'].get('도구', '?')}" + (f" · 같은 대화에서 {len(rs)}번 주움 (이어 읽기)" if len(rs) > 1 else ""))
        for r in rs:
            out.append(f"### [{r['id']}] {r['title']}")
            for k in keys:
                v = r["fields"].get(k)
                if v and v != "—":
                    out.append(f"- {k}: {v}")
            if r["approve"]:
                out.append(f"- 승인 체크: {'됨' if r['approve'][0] else '안 됨'} ({r['approve'][1]})")
        out.append("")
    print("\n".join(out))
    return 0


def run_record(args):
    env = dict(os.environ, MILLIE_HOME=str(ROOT))
    r = subprocess.run([sys.executable, str(RECORD_PY), *args], capture_output=True, text=True, env=env)
    return r.returncode == 0, (r.stdout or r.stderr).strip().splitlines()[-1:] or [""]


def set_field(block, key, value):
    """블록의 `- key: ...` 줄을 바꾸거나 para-id 앞에 넣는다."""
    line = f"- {key}: {value}"
    if re.search(rf"^- {re.escape(key)}:.*$", block, re.M):
        return re.sub(rf"^- {re.escape(key)}:.*$", line, block, count=1, flags=re.M)
    head, tail = block.rsplit("<!-- para-id:", 1)
    return head + line + "\n<!-- para-id:" + tail


def apply_item(vault, projs, area_map, topics, r, it, notes):
    """판정 항목 하나 → (dest 문자열, 대기 블록 또는 None, 오류 또는 None)."""
    kind, tgt = it.get("kind"), (it.get("target") or "").strip()
    line = one_line(it.get("line") or r["title"], 160)
    if kind == "project":
        if tgt not in projs:
            return None, None, f"없는 프로젝트 `{tgt}`"
        sec = it.get("section") if it.get("section") in DEVLOG_SECTIONS else "한 일"
        ok, msg = run_record(["devlog", "--project", tgt, "--section", sec, "--text", line])
        if not ok:
            return None, None, f"개발일지 실패: {msg[0]}"
        dest = [f"개발일지 · {sec}"]
        iss = it.get("issue") or {}
        if isinstance(iss, dict) and iss.get("line"):
            isec = iss.get("section") if iss.get("section") in ISSUE_SECTIONS else "프로젝트 이슈"
            ok, msg = run_record(["issue", "--project", tgt, "--section", isec, "--text", one_line(iss["line"], 160)])
            dest.append("이슈" if ok else "이슈(문서 없음 — 개발일지에만)")
        todos = [t for t in it.get("todos") or [] if isinstance(t, dict) and (t.get("text") or "").strip()]
        n = 0
        for t in todos:
            eff = t.get("effort") if t.get("effort") in EFFORTS else "🔸"
            n += run_record(["todo", "--project", tgt, "--text", one_line(t["text"], 160), "--effort", eff, "--background"])[0]
        if n:
            dest.append(f"할 일 {n}")
        return f"{link_project(vault, projs, tgt)} ({' · '.join(dest)})", None, None
    if kind in ("area", "resource"):
        pool = area_map if kind == "area" else topics
        if not tgt:
            return None, None, "대상 이름 없음"
        if tgt not in pool:                              # 새 영역 · 주제는 사용자 승인 뒤에만 — 인박스에 체크박스로 남긴다
            icon, word = ("🧵", "영역") if kind == "area" else ("📎", "자료 주제")
            b = r["block"]
            if "만들기 (체크하면" not in b:
                b = set_field(b, "대기", f"새 {word} 「{tgt}」 — 체크하면 다음 정리 때 만들고 옮긴다")
                head, tail = b.rsplit("<!-- para-id:", 1)
                b = head + f"- [ ] {icon} {tgt} {word} 만들기 (체크하면 다음 정리 때 생성)\n<!-- para-id:" + tail
            b = set_field(b, "대기 줄", line)
            return f"{icon} {tgt} 승인 대기 (PARA 인박스)", b, None
        args = ["area", "--name", tgt, "--text", line] if kind == "area" else ["resource", "--topic", tgt, "--text", line]
        ok, msg = run_record(args)
        if not ok:
            return None, None, f"{kind} 실패: {msg[0]}"
        p = area_map[tgt] if kind == "area" else topics[tgt] / f"📎 {tgt} 수집.md"
        icon = "🧵" if kind == "area" else "📎"
        return f"[[{p.relative_to(vault).with_suffix('')}|{icon} {tgt}]]", None, None
    return None, None, f"모르는 kind `{kind}`"


def cmd_apply(a):
    vault = config.vault()
    try:
        data = json.loads(pathlib.Path(a.apply).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        release()
        print(f"판정 파일을 못 읽음: {e}")
        return 2
    verdicts = {v.get("id"): v for v in (data.get("results") or []) if isinstance(v, dict)}
    recs = {r["id"]: r for r in pending_records()}
    projs, area_map, topics = projects(vault), areas(vault), resource_topics(vault)
    now = datetime.datetime.now()
    rows, changed, removed, notes = [], {}, set(), []
    stat = {"기록": 0, "건너뜀": 0, "보류": 0, "승인 대기": 0, "오류": 0}

    # 사용자가 체크한 승인 → 만들고 남겨 둔 줄을 넣는다
    for r in recs.values():
        if r["approve"] and r["approve"][0] and r["id"] not in verdicts:
            _, name, kind = r["approve"]
            ok, _m = run_record(["new", "area" if kind == "area" else "topic", "--name", name, "--approved"])
            area_map, topics = areas(vault), resource_topics(vault)
            it = {"kind": kind, "target": name, "line": r["fields"].get("대기 줄") or r["title"]}
            dest, _b, err = apply_item(vault, projs, area_map, topics, dict(r, block=r["block"]), it, notes)
            if dest and not _b:
                rows.append((r, dest, "승인"))
                removed.add(r["id"])
                stat["기록"] += 1

    for rid, v in verdicts.items():
        r = recs.get(rid)
        if not r or rid in removed:
            continue
        act = v.get("action")
        reason = one_line(v.get("reason") or "", 80)
        if act not in ACTIONS:
            changed[rid] = set_field(r["block"], "보류", f"판정 오류 — action `{act}` ({now:%Y-%m-%d})")
            stat["오류"] += 1
            continue
        if act == "skip":
            rows.append((r, f"건너뜀 ({reason or '기록할 일 아님'})", "AI"))
            removed.add(rid)
            stat["건너뜀"] += 1
            continue
        if act == "defer":
            changed[rid] = set_field(r["block"], "보류", f"{reason or '아직 안 끝남'} ({now:%Y-%m-%d})")
            stat["보류"] += 1
            continue
        dests, errs, wait = [], [], None
        for it in v.get("items") or []:
            if not isinstance(it, dict):
                continue
            dest, block, err = apply_item(vault, projs, area_map, topics, r, it, notes)
            if err:
                errs.append(err)
            elif block:
                wait = block
                r = dict(r, block=block)
                dests.append(dest)
            else:
                dests.append(dest)
        if wait:
            changed[rid] = wait
            stat["승인 대기"] += 1
            rows.append((r, " + ".join(dests), "AI"))      # 승인 대기 행은 히스토리에 안 쓴다 (아래에서 거름)
        elif dests:
            rows.append((r, " + ".join(dests), "AI" + (f"(일부 오류: {'; '.join(errs)})" if errs else "")))
            removed.add(rid)
            stat["기록"] += 1
        else:
            changed[rid] = set_field(r["block"], "보류", f"판정 오류 — {'; '.join(errs) or '항목 없음'} ({now:%Y-%m-%d})")
            stat["오류"] += 1

    hist_path = config.vpath("para_history")
    moved = [(r, d, h) for r, d, h in rows if r["id"] in removed]
    if moved:
        hist = hist_path.read_text(encoding="utf-8").rstrip("\n") if hist_path.exists() else history_header(f"{now:%Y-%m-%d}").rstrip("\n")
        block = [f"\n\n## {now:%Y-%m-%d %H:%M} · {len(moved)}건 · AI 정리"]
        block += [f"- {r['title']} → {d} · {h} <!-- para-id: {r['id']} -->" for r, d, h in moved]
        tmp = hist + "\n".join(block) + "\n"
        _atomic(hist_path, tmp)

    # 인박스는 지금 다시 읽어서 — 정리하는 동안 새로 쌓인 사건을 지우지 않는다
    inbox = config.vpath("para_inbox")
    header, cur = parse_inbox(inbox.read_text(encoding="utf-8"))
    keep = [changed.get(r["id"], r["block"]) for r in cur if r["id"] not in removed]
    _atomic(inbox, header + ("\n\n" + "\n\n".join(keep) if keep else "") + "\n")
    release()
    msg = " · ".join(f"{k} {n}" for k, n in stat.items()) + f" · 남은 대기 {len(keep)}"
    log("AI 정리 " + msg)
    print("PARA 정리 " + msg)
    return 0


def _atomic(path, text):
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, str(path))

def main():
    ap = argparse.ArgumentParser(description="PARA 분류기")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--no-slack", action="store_true")
    ap.add_argument("--pending", action="store_true", help="AI 가 판정할 대기 목록 출력 (para-sort 스킬)")
    ap.add_argument("--claim", action="store_true", help="--pending 과 같이: 정리 잠금 (다른 대화와 겹치지 않게)")
    ap.add_argument("--force", action="store_true", help="--claim 잠금을 무시")
    ap.add_argument("--apply", metavar="FILE", help="AI 판정 JSON 을 적용")
    ap.add_argument("--release", action="store_true", help="정리 잠금만 푼다")
    a = ap.parse_args()
    if a.release:
        release()
        return
    if a.pending:
        sys.exit(cmd_pending(a))
    if a.apply:
        sys.exit(cmd_apply(a))

    vault = config.vault()
    inbox = config.vpath("para_inbox")
    if not inbox.exists():
        print("PARA 인박스 없음")
        return
    header, recs = parse_inbox(inbox.read_text(encoding="utf-8"))
    hist_path = config.vpath("para_history")
    done_ids = set(re.findall(r"para-id: (\w+)", hist_path.read_text(encoding="utf-8"))) if hist_path.exists() else set()
    already = [r for r in recs if r["id"] in done_ids]
    recs = [r for r in recs if r["id"] not in done_ids]
    if not recs and not already:
        print("PARA 인박스 비어 있음")
        return

    projs, area_map, topics = projects(vault), areas(vault), resource_topics(vault)
    use_llm = not a.no_llm
    blocked = None
    if use_llm:
        ok, why = llm.llm_allowed()
        if not ok:
            use_llm, blocked = False, why
            log(f"LLM 차단: {why}")

    # 같은 대화가 여러 번 주워졌으면(대화가 길어 수집이 나눠 봄) 마지막 것만 넣고 앞의 것은 합친 것으로 친다
    def convo(r):
        m = re.search(r"`([^`]+)`", r["fields"].get("기록", ""))
        return m.group(1) if m else r["id"]
    last = {}
    for r in recs:
        last[convo(r)] = r["id"]
    dups = [r for r in recs if not r["approve"] and last[convo(r)] != r["id"]]
    recs = [r for r in recs if r not in dups]

    # 승인 체크된 대기 사건은 판정 없이 그 영역으로
    approved = [r for r in recs if r["approve"] and r["approve"][0]]
    waiting = [r for r in recs if r["approve"] and not r["approve"][0]]
    fresh = [r for r in recs if not r["approve"]]
    decided, source, error = decide(fresh, projs, area_map, topics, keyword_rules(vault), use_llm) if fresh else ([], "off", None)
    for r in approved:
        name = r["approve"][1]
        if r["approve"][2] != "area":
            continue
        decided.append((r, {"id": r["id"], "kind": "area", "target": name, "new_area": name not in area_map,
                            "approved": True, "how": "승인", "note_line": f"{r['title']} — {r['fields'].get('요약', '')}"}))

    now = datetime.datetime.now()
    today = f"{now:%Y-%m-%d}"
    dev_lines, issue_lines, notes, created, keep, rows = [], [], [], [], [], []
    for r, v in decided:
        k, tgt = v["kind"], v.get("target", "")
        if k == "project":
            dev_lines.append(inbox_line(now, tgt, v.get("devlog_section") or "한 일", v.get("devlog_line") or r["title"]))
            dest = [f"개발일지 · {v.get('devlog_section') or '한 일'}"]
            if v.get("issue_section") in ISSUE_SECTIONS and v.get("issue_line"):
                issue_lines.append(inbox_line(now, tgt, v["issue_section"], v["issue_line"]))
                dest.append("이슈")
            todos = [t for t in v.get("todos") or [] if t.strip()]
            dev_lines += [inbox_line(now, tgt, "내일", t) for t in todos]
            if todos:
                dest.append(f"할 일 {len(todos)}")
            rows.append((r, f"{link_project(vault, projs, tgt)} ({' · '.join(dest)})", v["how"]))
        elif k == "area":
            path = area_map.get(tgt) or config.vpath("areas") / f"🧵 {tgt}.md"
            if tgt not in area_map and not v.get("approved"):
                keep.append(with_approval(r["block"], tgt))      # Q11: 승인 전엔 만들지 않고 대기
                rows.append((r, f"🧵 {tgt} 승인 대기 (PARA 인박스)", v["how"]))
                continue
            if tgt not in area_map:
                created.append(path)
            notes.append((path, f"- {today} {one_line(v.get('note_line') or r['title'])} ({r['fields'].get('도구', '')})", "area"))
            rows.append((r, f"[[{path.relative_to(vault).with_suffix('')}|🧵 {tgt}]]", v["how"]))
        else:
            d = topics[tgt]
            path = d / f"📎 {tgt} 수집.md"
            notes.append((path, f"- {today} {one_line(v.get('note_line') or r['title'])} ({r['fields'].get('도구', '')})", ("resource", tgt)))
            rows.append((r, f"[[{path.relative_to(vault).with_suffix('')}|📎 {tgt}]]", v["how"]))
    keep += [r["block"] for r in waiting]

    llm_label = f"차단({blocked})" if blocked else (source if not error else f"실패({error})")
    if a.dry_run:
        for r, dest, how in rows:
            print(f"- {r['title']} → {dest} · {how}")
        for ln in dev_lines:
            print("  로그 인박스 +", ln)
        for ln in issue_lines:
            print("  이슈 인박스 +", ln)
        for p, b, _ in notes:
            print(f"  {p.relative_to(vault)} +", b)
        print(f"[dry-run] 사건 {len(rows)}건 · 대기 {len(waiting)} · 이미 처리 {len(already)} · LLM {llm_label}")
        return

    append_lines(config.vpath("devlog_inbox"), dev_lines)
    append_lines(config.vpath("issue_inbox"), issue_lines)
    for path, bullet, kind in notes:
        if not path.exists():
            if kind == "area":
                path.write_text(AREA_TEMPLATE.format(today=today, resources=config.load()["paths"]["resources"]), encoding="utf-8")
            else:
                path.write_text(RESOURCE_TEMPLATE.format(today=today, topic=kind[1]), encoding="utf-8")
        add_note_line(path, bullet)

    rows += [(r, "같은 대화의 뒤 기록에 합침", "합침") for r in dups]
    moved = [(r, dest, how) for r, dest, how in rows if "승인 대기" not in dest]
    if moved or rows:
        hist = hist_path.read_text(encoding="utf-8").rstrip("\n") if hist_path.exists() else history_header(today).rstrip("\n")
        block = [f"\n\n## {now:%Y-%m-%d %H:%M} · {len(moved)}건 · LLM {llm_label}"]
        block += [f"- {r['title']} → {dest} · {how} <!-- para-id: {r['id']} -->" for r, dest, how in moved]
        hist_path.write_text(hist + "\n".join(block) + "\n", encoding="utf-8")

    inbox.write_text(header + ("\n\n" + "\n\n".join(keep) if keep else "") + "\n", encoding="utf-8")

    slack = "건너뜀"
    if not a.no_slack and rows:
        lines = [f"*PARA 분류* {len(moved)}건 · LLM {llm_label}"]
        lines += ["• " + r["title"] + " → " + WIKILINK.sub(r"\1", dest) for r, dest, how in rows]
        if any("승인 대기" in d for _, d, _ in rows):
            lines.append("새 영역 승인: vault 루트 `📥 PARA 인박스` 에서 체크하면 다음 분류 때 만든다")
        lines.append("틀린 곳은 옮겨주세요 — `📤 PARA 이동 히스토리`")
        slack = send_slack("\n".join(lines))
    msg = (f"분류 {len(moved)}건 · 대기 {len(keep)} · 새 영역 {len(created)} · 이미 처리 {len(already)} · "
           f"LLM {llm_label} · Slack {slack}")
    log(msg)
    print(msg)


if __name__ == "__main__":
    main()
