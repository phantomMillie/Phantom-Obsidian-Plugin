#!/usr/bin/env python3
# PARA 수집기 — AI 도구 대화 기록에서 "끝난 사건"만 골라 vault 루트 `📥 PARA 인박스.md` 에 적립한다.
# 규격: PARA 프레임워크 규격서 (config `paths.spec_doc`). vault 경로 · 이름은 전부 config.json
#
#   python3 collect.py --dry-run          판단 결과만 출력. 인박스 · 상태 파일 안 건드림
#   python3 collect.py                    적립 + 상태 갱신
#     --since-hours N   상태 파일에 없는 세션은 최근 N시간 안에 바뀐 것만 본다 (기본 24)
#     --limit N         한 번에 볼 세션 수 (기본 20, 최근 것부터. --no-llm 이면 제한 없음)
#     --no-llm          LLM 없이: 끝 신호가 있는 세션만 세션 1건 = 사건 1건으로 적립 (요약 = 마지막 AI 응답)
#
# 수집 대상 (자동화 세션 제외 — 수집기 자신의 LLM 호출도 여기서 걸러진다):
#   Claude Code  ~/.claude/projects/*/*.jsonl   entrypoint == "cli"     (sdk-cli = claude -p 자동화)
#   Codex        ~/.codex/sessions/**/*.jsonl    source in {cli, vscode} (exec = codex exec 자동화)
#   Gemini       ~/.gemini/tmp/*/chats/*.json(l)  구 형식(messages 배열) · 신 형식(.jsonl, `$set` 갱신)
#
# 사건 경계 · 끝 판정 (Q8): 끝 신호 ① 사용자가 끝났다고 말함 ② 커밋 · PR ③ AI 작업 완료 보고
#   → 신호는 LLM에게 힌트로 주고, LLM이 사건을 나누고 끝났는지 판단한다. 무활동은 끝 신호로 안 쓴다.
# 세션마다 "어디까지 적립했나"(cursor)를 상태 파일에 남긴다. 안 끝난 사건은 다음 실행 때 다시 본다.
#
# 외부 LLM 조건(Q15) · 호출 경로는 llm.py — 학습 안 하는 계약일 때만 LLM 을 부른다.
import argparse, datetime, glob, hashlib, json, os, pathlib, re, shlex, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config, llm  # noqa: E402

HOME = pathlib.Path.home()
ROOT = pathlib.Path(__file__).resolve().parent.parent           # ~/.millie-obsidian
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "collect.json"
LOG_FILE = STATE_DIR / "collect.log"


MIN_LINES = 6                     # Q4: 6줄 미만 세션 제외 (convo-digest session-end.mjs:19 와 같은 기준)
TURN_CHARS = 2000                 # 턴 하나가 LLM에 들어가는 최대 글자 — 긴 AI 설명은 앞부분만
CHUNK_CHARS = 120_000             # 한 번에 LLM에 보내는 최대 분량. 넘으면 앞에서부터 잘라 다음 실행에 이어 본다

TOOL_LABEL = {"claude": "Claude Code", "codex": "Codex", "gemini": "Gemini"}
SIGNAL_LABEL = {"user-ack": "사용자 말", "commit": "커밋/PR", "ai-done": "AI 완료 보고", "llm": "LLM 판단"}

# ── 비밀값 가림 (Q4) ─────────────────────────────────────────────
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[개인키 가림]"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"), "[키 가림]"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), "[키 가림]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "[토큰 가림]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "[토큰 가림]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[키 가림]"),
    (re.compile(r"https://hooks\.slack\.com/services/\S+"), "[웹훅 가림]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "[토큰 가림]"),
    (re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|secret|password|passwd)(\s*[:=]\s*)['\"]?[^\s'\"]{6,}"), r"\1\2[가림]"),
    (re.compile(r"\b\d{6}-[1-4]\d{6}\b"), "[주민번호 가림]"),
    (re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"), "[전화번호 가림]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[이메일 가림]"),
]

def mask(text):
    for pat, rep in SECRET_PATTERNS:
        text = pat.sub(rep, text)
    return text

# ── 끝 신호 (Q8) ─────────────────────────────────────────────────
USER_ACK = re.compile(r"(됐다|됐어|됐네|됐음|해결\s*(됐|했|됨)|완료\s*(했|됐|됨|$)|끝났|끝냈|고마워|감사|ㄳ|ㄱㅅ|잘\s*되(네|는|어)|잘\s*된다|머지\s*(했|됐)|lgtm)", re.I)
COMMIT = re.compile(r"\bgit\s+(-C\s+\S+\s+)?commit\b")
PR_CREATE = re.compile(r"\bgh\s+pr\s+create\b")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
NOISE_PREFIX = ("<command-", "<local-command", "<system-reminder", "<environment_context", "<user_instructions",
                "# AGENTS.md", "Caveat:", "<task-notification")


def log(msg):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")




# ── 세션 읽기: 도구별 → 공통 형태 ────────────────────────────────
# session = {tool, path, id, cwd, title, lines, turns:[{role, text, ts, files, commit, pr, done}]}

def _new_turn(role, ts):
    return {"role": role, "text": "", "ts": ts or "", "files": [], "commit": False, "pr": None, "done": False, "recorded": []}


VAULT_RECORD = re.compile(r"vault_record\.py\s+(devlog|todo|tick|area|resource|issue)\b")


def _recorded(cmd):
    """AI 가 그 턴에 바로 기록한 것(vault_record 호출) → 한 줄 요약. 아니면 None."""
    m = VAULT_RECORD.search(cmd or "")
    if not m:
        return None
    try:
        args = shlex.split(cmd[m.end():].split("&&")[0].split(";")[0])
    except ValueError:
        args = cmd[m.end():].split()
    opt = {}
    for k, v in zip(args, args[1:] + [""]):
        if k.startswith("--"):
            opt[k[2:]] = v
    head = " · ".join(x for x in (opt.get("project") or opt.get("name") or opt.get("topic"), opt.get("section")) if x)
    body = opt.get("text") or opt.get("item") or ""
    return f"{m.group(1)} {head} · {body}".strip(" ·")


def _add_text(turn, text):
    text = (text or "").strip()
    if text:
        turn["text"] = (turn["text"] + "\n" + text).strip()


def _is_noise(text):
    return text.lstrip().startswith(NOISE_PREFIX)


def read_claude(path):
    s = {"tool": "claude", "path": str(path), "id": path.stem, "cwd": "", "title": "", "lines": 0, "turns": []}
    entry = None
    cur = None
    for raw in path.open(encoding="utf-8", errors="replace"):
        if not raw.strip():
            continue
        s["lines"] += 1
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            continue
        t = d.get("type")
        if t == "ai-title":
            s["title"] = d.get("aiTitle") or s["title"]
        elif t == "pr-link":
            if cur is not None:
                cur["pr"] = d.get("prUrl")
        if t not in ("user", "assistant") or d.get("isSidechain"):
            continue
        entry = entry or d.get("entrypoint")
        s["cwd"] = s["cwd"] or d.get("cwd", "")
        content = d.get("message", {}).get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])
        if t == "user":
            texts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
            texts = [x for x in texts if x.strip() and not _is_noise(x)]
            if not texts:
                continue                                         # tool_result 만 있는 기록 = 사용자 발화 아님
            cur = _new_turn("user", d.get("timestamp"))
            for x in texts:
                _add_text(cur, x)
            s["turns"].append(cur)
        else:
            if cur is None or cur["role"] != "assistant":
                cur = _new_turn("assistant", d.get("timestamp"))
                s["turns"].append(cur)
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text":
                    _add_text(cur, b.get("text"))
                elif b.get("type") == "tool_use":
                    inp = b.get("input") or {}
                    if b.get("name") in EDIT_TOOLS and inp.get("file_path"):
                        cur["files"].append(inp["file_path"])
                    cmd = inp.get("command") if isinstance(inp.get("command"), str) else ""
                    if COMMIT.search(cmd):
                        cur["commit"] = True
                    if PR_CREATE.search(cmd):
                        cur["pr"] = cur["pr"] or "PR 생성"
                    rec = _recorded(cmd)
                    if rec:
                        cur["recorded"].append(rec)
    if entry != "cli":
        return None
    return s


def _patch_files(text):
    return re.findall(r"^\*\*\* (?:Update|Add) File: (.+)$", text or "", re.M)


def read_codex(path):
    s = {"tool": "codex", "path": str(path), "id": path.stem, "cwd": "", "title": "", "lines": 0, "turns": []}
    source = None
    cur = None
    for raw in path.open(encoding="utf-8", errors="replace"):
        if not raw.strip():
            continue
        s["lines"] += 1
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            continue
        p = d.get("payload") or {}
        if d.get("type") == "session_meta":
            source = str(p.get("source"))
            s["cwd"] = p.get("cwd", "")
            s["id"] = p.get("id") or s["id"]
        elif d.get("type") == "response_item" and p.get("type") == "message":
            role = p.get("role")
            if role not in ("user", "assistant"):
                continue
            texts = [b.get("text", "") for b in p.get("content") or [] if isinstance(b, dict)]
            texts = [x for x in texts if x.strip() and not _is_noise(x)]
            if not texts:
                continue
            if cur is None or cur["role"] != role or role == "user":
                cur = _new_turn(role, d.get("timestamp"))
                s["turns"].append(cur)
            for x in texts:
                _add_text(cur, x)
        elif d.get("type") == "response_item" and p.get("type") in ("function_call", "custom_tool_call"):
            if cur is None or cur["role"] != "assistant":
                cur = _new_turn("assistant", d.get("timestamp"))
                s["turns"].append(cur)
            arg = p.get("arguments") or p.get("input") or ""
            arg = arg if isinstance(arg, str) else json.dumps(arg, ensure_ascii=False)
            cur["files"] += _patch_files(arg)
            try:
                cmdv = json.loads(arg).get("command") if arg.lstrip().startswith("{") else None
            except json.JSONDecodeError:
                cmdv = None
            rec = _recorded(" ".join(cmdv) if isinstance(cmdv, list) else (cmdv or arg))
            if rec:
                cur["recorded"].append(rec)
            if COMMIT.search(arg):
                cur["commit"] = True
            if PR_CREATE.search(arg):
                cur["pr"] = cur["pr"] or "PR 생성"
        elif d.get("type") == "event_msg" and p.get("type") == "task_complete":
            if cur is not None and cur["role"] == "assistant":
                cur["done"] = True
    if source not in ("cli", "vscode"):
        return None
    return s


def _gemini_jsonl(path):
    """신 형식: 첫 줄 메타, 그 뒤 `{"$set": {"messages": [...]}}` 갱신(마지막이 최신) 또는 메시지 한 줄씩."""
    meta, msgs = {}, []
    for raw in path.open(encoding="utf-8", errors="replace"):
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(d, dict):
            continue
        if "sessionId" in d and "type" not in d:
            meta = d
        elif isinstance((d.get("$set") or {}).get("messages"), list):
            msgs = d["$set"]["messages"]
        elif isinstance((d.get("$push") or {}).get("messages"), (list, dict)):
            v = d["$push"]["messages"]
            msgs += v if isinstance(v, list) else [v]
        elif d.get("type") and "content" in d:
            msgs.append(d)
    return {"sessionId": meta.get("sessionId"), "messages": msgs}


def _gemini_text(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text", "") for b in c if isinstance(b, dict))
    return ""


def read_gemini(path):
    if path.suffix == ".jsonl":
        d = _gemini_jsonl(path)
    else:
        try:
            d = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return None
    msgs = d.get("messages") if isinstance(d, dict) else None
    if not isinstance(msgs, list):
        return None
    s = {"tool": "gemini", "path": str(path), "id": d.get("sessionId") or path.stem,
         "cwd": "", "title": "", "lines": len(msgs) * 2, "turns": []}
    for m in msgs:
        role = {"user": "user", "gemini": "assistant", "model": "assistant", "assistant": "assistant"}.get(m.get("type"))
        text = _gemini_text(m.get("content"))
        if not role or not text.strip() or _is_noise(text):
            continue
        t = _new_turn(role, m.get("timestamp"))
        _add_text(t, text)
        s["turns"].append(t)
    return s


SOURCES = [
    ("claude", lambda: glob.glob(str(HOME / ".claude/projects/*/*.jsonl")), read_claude),
    ("codex", lambda: glob.glob(str(HOME / ".codex/sessions/**/*.jsonl"), recursive=True), read_codex),
    ("gemini", lambda: glob.glob(str(HOME / ".gemini/tmp/*/chats/*.json")) + glob.glob(str(HOME / ".gemini/tmp/*/chats/*.jsonl")), read_gemini),
]


def mark_signals(s):
    """턴마다 끝 신호를 붙인다. LLM 힌트이자 --no-llm 판정 근거."""
    for i, t in enumerate(s["turns"]):
        sig = []
        if t["role"] == "user" and USER_ACK.search(t["text"]):
            sig.append("user-ack")
        if t["commit"] or t["pr"]:
            sig.append("commit")
        nxt = s["turns"][i + 1] if i + 1 < len(s["turns"]) else None
        if t["role"] == "assistant" and (t["done"] or (t["files"] and (nxt is None or nxt["role"] == "user"))):
            sig.append("ai-done")
        t["signals"] = sig


# ── LLM ───────────────────────────────────────────────────────────
EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_turn": {"type": "integer"},
                    "end_turn": {"type": "integer"},
                    "title": {"type": "string"},
                    "feature": {"type": "string"},
                    "work": {"type": "boolean"},
                    "ended": {"type": "boolean"},
                    "end_reason": {"type": "string", "enum": ["해결", "작업 완료", "미종료"]},
                    "end_signal": {"type": "string", "enum": ["user-ack", "commit", "ai-done", "llm", "none"]},
                    "summary": {"type": "string"},
                    "resolved": {"type": "array", "items": {"type": "string"}},
                    "unresolved": {"type": "array", "items": {"type": "string"}},
                    "files": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["start_turn", "end_turn", "title", "feature", "work", "ended", "end_reason",
                             "end_signal", "summary", "resolved", "unresolved", "files"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["events"],
    "additionalProperties": False,
}

PROMPT = """아래는 개발자와 AI 코딩 도구의 대화 기록이다. 턴 번호 [n]이 붙어 있다.
대화를 **사건** 단위로 나눠라. 사건 = 한 피쳐에서 나온 하나의 문제나 AI 작업.
사건은 문제가 해결됐거나 AI 작업이 마무리되면 끝난다.
사건은 시간 순서대로, 서로 턴이 겹치지 않게 나눈다. 한 작업 도중의 곁가지(오판 기록 · 중간 확인 등)는 따로 떼지 말고 그 작업 사건에 넣는다.

끝 신호 힌트가 턴 끝에 `{{신호: ...}}` 로 붙어 있다 — user-ack(사용자가 끝났다고 말함) · commit(커밋/PR) · ai-done(AI가 파일을 고치고 마무리 보고).
힌트는 참고만 하고, 대화를 읽고 판단하라. 힌트가 없어도 끝났으면 end_signal 은 "llm".
아직 진행 중이거나 다음 턴에서 이어질 것 같으면 ended=false, end_reason="미종료", end_signal="none".
"한동안 대화가 없었다"는 끝난 이유가 아니다.

각 사건:
- start_turn / end_turn: 사건이 걸친 턴 번호
- title: 한 줄 제목 (한국어)
- feature: 사건이 나온 피쳐 · 프로젝트 이름. 대화에서 확인되는 이름만, 모르면 ""
- work: 업무 사건이면 true. 잡담 · 업무 외 · 단순 확인 질문이면 false
- ended / end_reason("해결" 또는 "작업 완료") / end_signal
- summary: 결론 1~3문장. 무엇을 했고 어떻게 끝났나
- resolved / unresolved: 해결된 것 · 남은 것 (짧게, 없으면 빈 배열)
- files: 이 사건에서 만들거나 고친 파일 경로 (기록에 나온 것만)

대화에 없는 내용을 지어내지 마라. 비밀값은 이미 가려져 있다.
JSON 객체 {"events": [...]} 하나만 출력하라.

작업 폴더: {cwd}
세션 제목: {title}

{transcript}"""


def render_transcript(s, start):
    out, size, last = [], 0, start - 1
    for i in range(start, len(s["turns"])):
        t = s["turns"][i]
        who = "사용자" if t["role"] == "user" else "AI"
        body = mask(t["text"])[:TURN_CHARS]
        extra = []
        if t["files"]:
            extra.append("고친 파일: " + ", ".join(sorted(set(t["files"]))[:12]))
        if t["commit"]:
            extra.append("커밋함")
        if t["pr"]:
            extra.append(f"PR: {t['pr']}")
        if t["signals"]:
            extra.append("{{신호: " + ", ".join(t["signals"]) + "}}")
        line = f"[{i}] {who}: {body}" + ("\n    " + " · ".join(extra) if extra else "")
        if out and size + len(line) > CHUNK_CHARS:
            break
        out.append(line)
        size += len(line)
        last = i
    return "\n".join(out), last


def llm_events(s, start):
    transcript, last = render_transcript(s, start)
    prompt = (PROMPT.replace("{cwd}", s["cwd"] or "-").replace("{title}", mask(s["title"]) or "-")
              .replace("{transcript}", transcript))
    data, _ = llm.call(prompt, EVENT_SCHEMA)
    return data.get("events", []), last


# ── 사건 → 인박스 기록 ────────────────────────────────────────────

def event_id(s, start, end):
    return hashlib.sha1(f"{s['path']}|{start}|{end}".encode()).hexdigest()[:12]


DIALOG_CHARS = 2400


def dialog(s, start, end):
    """판정하는 AI 가 읽을 대화 발췌 — 사용자 말 · AI 답을 턴마다 짧게.
    길면 일한 턴(파일 수정 · 커밋 · 바로 기록)과 그 앞뒤를 먼저 담고, 남는 자리에 처음 · 끝을 채운다 —
    긴 잡담 사이에 낀 실제 작업이 잘려 나가지 않게."""
    idx = [i for i in range(start, end + 1) if s["turns"][i]["text"]]
    if len(idx) > 14:
        work = [i for i in idx if s["turns"][i]["files"] or s["turns"][i]["commit"] or s["turns"][i]["pr"] or s["turns"][i].get("recorded")]
        keep = set()
        for i in work:
            keep.update(j for j in (i - 1, i, i + 1) if start <= j <= end)
        for i in idx[:2] + idx[-4:]:
            if len(keep) >= 14:
                break
            keep.add(i)
        idx = sorted(i for i in idx if i in keep)
    rows, prev = [], None
    for i in idx:
        if prev is not None and i > prev + 1:
            rows.append(f"… {i - prev - 1}턴 생략 …")
        t = s["turns"][i]
        who = "사용자" if t["role"] == "user" else "AI"
        rows.append(f"[{i}] {who}: " + one_line(mask(t["text"]), 220 if who == "사용자" else 260))
        prev = i
    out = " ‖ ".join(rows)
    return out if len(out) <= DIALOG_CHARS else out[:DIALOG_CHARS - 1] + "…"


def to_record(s, ev):
    files = ev.get("files") or []
    turns = s["turns"][ev["start_turn"]:ev["end_turn"] + 1]
    if not files:
        for t in turns:
            files += t["files"]
    return {
        "cwd": s.get("cwd") or "",
        "dialog": dialog(s, ev["start_turn"], ev["end_turn"]),
        "recorded": [mask(x) for t in turns for x in t.get("recorded", [])],
        "id": event_id(s, ev["start_turn"], ev["end_turn"]),
        "tool": TOOL_LABEL[s["tool"]],
        "path": s["path"],
        "turns": f"{ev['start_turn']}–{ev['end_turn']}",
        "feature": mask(ev.get("feature") or ""),
        "title": mask(ev.get("title") or s["title"] or "(제목 없음)"),
        "end_reason": ev.get("end_reason") or "작업 완료",
        "end_signal": ev.get("end_signal") or "llm",
        "summary": mask(ev.get("summary") or ""),
        "resolved": [mask(x) for x in ev.get("resolved") or []],
        "unresolved": [mask(x) for x in ev.get("unresolved") or []],
        "files": sorted(set(files))[:30],
    }


def fallback_events(s, start):
    """--no-llm: 끝 신호가 있는 마지막 턴까지를 사건 1건으로."""
    ends = [i for i in range(start, len(s["turns"])) if s["turns"][i]["signals"]]
    if not ends:
        return [], start - 1
    end = ends[-1]
    span = s["turns"][start:end + 1]
    worked = [t for t in span if t["role"] == "assistant" and t["text"] and (t["files"] or t["commit"] or t["pr"])]
    last_ai = (worked or [t for t in span if t["role"] == "assistant" and t["text"]] or [{"text": ""}])[-1]["text"]   # 요약 = 마지막으로 일한 답
    sig = s["turns"][end]["signals"][0]
    return [{"start_turn": start, "end_turn": end, "title": s["title"] or s["turns"][start]["text"][:60],
             "feature": "", "work": True, "ended": True,
             "end_reason": "해결" if sig == "user-ack" else "작업 완료", "end_signal": sig,
             "summary": last_ai[:400], "resolved": [], "unresolved": [], "files": []}], end


def one_line(text, limit=400):
    """인박스 한 항목 = 한 줄. 마크다운 제목 · 표 · 구분선은 버린다 (## 줄이 섞이면 새 사건으로 읽힘)."""
    keep = [ln.strip() for ln in (text or "").splitlines()
            if ln.strip() and not re.match(r"^\s*(#|\||-{3,}|```)", ln)]
    s = re.sub(r"\s+", " ", " ".join(keep)).strip()
    return s if len(s) <= limit else s[:limit - 1] + "…"


def session_project(path):
    """프롬프트 입력 훅이 정해 둔 이 대화의 (프로젝트, 근거) (state/session-projects.json). 없으면 (None, None)."""
    try:
        sp = json.loads((STATE_DIR / "session-projects.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    v = (sp.get("sessions") or {}).get(pathlib.Path(path).stem) or {}
    how = v.get("how")
    if v.get("folder"):
        how = f"{how} · 작업 폴더는 {v['folder']}"
    return v.get("project"), how


def render_record(r, now):
    proj, how = session_project(r["path"])
    if proj:                                    # 프롬프트 입력 때 정한 프로젝트 — 판정하는 AI 에게 근거와 같이 준다
        r = dict(r, feature=proj)
    r = dict(r, title=one_line(r["title"], 120), feature=one_line(r["feature"], 80), summary=one_line(r["summary"]),
             resolved=[one_line(x, 160) for x in r["resolved"]], unresolved=[one_line(x, 160) for x in r["unresolved"]])
    sig = SIGNAL_LABEL.get(r["end_signal"], r["end_signal"])
    lines = [f"## {r['title']}",
             f"- 도구: {r['tool']}",
             f"- 기록: `{r['path']}` (턴 {r['turns']})",
             f"- 피쳐: {r['feature'] or '—'}",
             f"- 종료: {r['end_reason']} · 끝 신호: {sig}",
             f"- 요약: {r['summary'] or '—'}"]
    if proj:
        lines.append(f"- 대화 프로젝트: {proj} (근거: {how or '—'})")
    if r.get("cwd"):
        lines.append(f"- 폴더: `{r['cwd']}`")
    if r.get("dialog"):
        lines.append(f"- 대화: {one_line(r['dialog'], DIALOG_CHARS)}")
    if r.get("recorded"):
        lines.append("- 이미 기록: " + " / ".join(one_line(x, 200) for x in r["recorded"]))
    if r["resolved"]:
        lines.append("- 해결: " + " / ".join(r["resolved"]))
    if r["unresolved"]:
        lines.append("- 미해결: " + " / ".join(r["unresolved"]))
    if r["files"]:
        lines.append("- 파일: " + ", ".join(f"`{f}`" for f in r["files"]))
    lines.append(f"- 수집: {now:%Y-%m-%d %H:%M}")
    lines.append(f"<!-- para-id: {r['id']} -->")
    return "\n".join(lines)


INBOX_HEADER = """---
type: para-inbox
created: {today}
tags: [para, inbox]
---

# 📥 PARA 인박스
> 수집기가 AI 대화에서 **끝난 사건**만 골라 여기 쌓는다. 분류기가 읽어 PARA 위치로 옮기고 비운다 — 직접 고치지 말 것.
{spec}"""


def spec_line():
    spec = config.vpath("spec_doc")
    if not spec:
        return ""
    rel = spec.relative_to(config.vault()).with_suffix("")
    return f"> 규격: [[{rel}|{spec.stem}]]\n"


def append_inbox(vault, records, now):
    inbox = config.vpath("para_inbox")
    existing = inbox.read_text(encoding="utf-8") if inbox.exists() else INBOX_HEADER.format(today=f"{now:%Y-%m-%d}", spec=spec_line())
    fresh = [r for r in records if f"para-id: {r['id']}" not in existing]
    if not fresh:
        return 0
    text = existing.rstrip("\n") + "\n\n" + "\n\n".join(render_record(r, now) for r in fresh) + "\n"
    inbox.write_text(text, encoding="utf-8")
    return len(fresh)


# ── 실행 ──────────────────────────────────────────────────────────

def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sessions": {}}


def candidates(state, since_hours, limit):
    now = datetime.datetime.now().timestamp()
    cutoff = now - since_hours * 3600
    if state.get("last_run"):                  # 지난번 이후 바뀐 대화는 다 본다 — 며칠 안 돌았어도(주말) 빠뜨리지 않게
        cutoff = min(cutoff, state["last_run"] - 3600)
    known = state["sessions"]
    out = []
    for tool, lister, reader in SOURCES:
        for p in lister():
            try:
                mtime = os.path.getmtime(p)
            except OSError:
                continue
            prev = known.get(p)
            if prev is None and mtime < cutoff:
                continue
            if prev is not None and mtime <= prev.get("mtime", 0):
                continue
            out.append((mtime, tool, pathlib.Path(p), reader))
    out.sort(key=lambda x: x[0], reverse=True)
    return out[:limit] if limit else out


def main():
    ap = argparse.ArgumentParser(description="PARA 수집기")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--since-hours", type=float, default=24)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--only", default="", help="경로에 이 문자열이 든 세션만 (시험용)")
    a = ap.parse_args()

    vault = config.vault()
    state = load_state()
    if not a.no_llm:
        ok, why = llm.llm_allowed()
        print(("LLM 사용: " if ok else "LLM 안 씀 → 끝 신호 기준만: ") + why)
        if not ok:
            log(f"LLM 차단: {why}")
            a.no_llm = True
    now = datetime.datetime.now()
    records, skipped, failed = [], {"자동화": 0, "짧음": 0, "새 턴 없음": 0}, []
    updates = {}

    limit = 0 if (a.no_llm or a.only) else a.limit           # LLM 없이는 싸다 — 바뀐 대화는 다 본다
    for mtime, tool, path, reader in candidates(state, a.since_hours, limit):
        if a.only and a.only not in str(path):
            continue
        s = reader(path)
        if s is None:
            skipped["자동화"] += 1
            updates[str(path)] = {"mtime": mtime, "cursor": 0, "skip": "automation"}
            continue
        if s["lines"] < MIN_LINES:
            skipped["짧음"] += 1
            continue                                            # 아직 짧은 세션은 자라면 다시 본다
        start = state["sessions"].get(str(path), {}).get("cursor", 0)
        if start >= len(s["turns"]):
            skipped["새 턴 없음"] += 1
            updates[str(path)] = {"mtime": mtime, "cursor": start}
            continue
        mark_signals(s)
        try:
            events, seen = fallback_events(s, start) if a.no_llm else llm_events(s, start)
        except RuntimeError as e:
            failed.append(f"{TOOL_LABEL[tool]} {path.name}: {e}")
            log(f"LLM 실패 {path}: {e}")
            continue                                            # cursor 그대로 → 다음 실행에 재시도
        cursor = start
        taken_end = start - 1                                   # 겹치는 사건은 버린다 (앞 사건에 이미 포함)
        for ev in sorted(events, key=lambda e: (e.get("start_turn", 0), -e.get("end_turn", 0))):
            if not ev.get("ended"):
                continue
            begin, end = int(ev.get("start_turn", -1)), int(ev.get("end_turn", -1))
            if end < start or end >= len(s["turns"]) or begin <= taken_end:
                continue
            taken_end = end
            cursor = max(cursor, end + 1)
            if ev.get("work"):
                records.append(to_record(s, ev))
        # 청크를 다 봤는데 끝난 사건이 없으면 cursor 는 그대로 — 사건이 끝날 때까지 기다린다
        updates[str(path)] = {"mtime": mtime, "cursor": cursor}

    if a.dry_run:
        for r in records:
            print(render_record(r, now), "\n")
        print(f"[dry-run] 사건 {len(records)}건 · 건너뜀 {skipped} · 실패 {len(failed)}")
        for f in failed:
            print("  실패:", f)
        return

    added = append_inbox(vault, records, now) if records else 0
    state["sessions"].update(updates)
    state["last_run"] = now.timestamp()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    msg = f"적립 {added}건 · 건너뜀 {skipped} · 실패 {len(failed)}"
    log(msg)
    print(msg)
    for f in failed:
        print("  실패:", f)


if __name__ == "__main__":
    main()
