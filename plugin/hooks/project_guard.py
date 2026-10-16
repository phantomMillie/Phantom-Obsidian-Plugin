#!/usr/bin/env python3
"""프로젝트 필수 항목(완료 조건 · 마일스톤 · 완료일) 리마인드 훅.

  SessionStart      → 비어 있는 활성 프로젝트 전부 (빠진 항목별로 묶어 이름을 다 보인다)
  UserPromptSubmit  → 프롬프트에 프로젝트 이름이 나오면, 그 프로젝트가 비었을 때 세션당 1번 상기

SessionStart 때 scripts/bootstrap.py 도 부른다 — 플러그인만 받은 PC 에 vault · TODO 앱을 깐다.
점검 로직은 플러그인의 `scripts/project_lint.py` (vault-init 이 vault `.scripts/` 에도 사본을 둔다).
vault·스크립트가 없거나 실패하면 아무것도 안 낸다 — 훅이 세션을 막지 않는다.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
from millie_home import load_config, millie_home      # noqa: E402

PLUGIN = pathlib.Path(__file__).resolve().parent.parent  # 캐시 사본일 수 있다 — 코드만 여기서 읽는다
HOME = millie_home(__file__)                            # config.json · state 는 늘 실제 홈에서
STATE = HOME / "state" / "guard.json"


def bootstrap():
    """처음 받은 PC 준비 — vault 는 바로 만들고, 나머지(Obsidian 설정 · TODO 앱)는 뒤에서 돌린다."""
    script = PLUGIN / "scripts" / "bootstrap.py"
    subprocess.run([sys.executable, str(script), "--fast"], capture_output=True, timeout=8)
    subprocess.Popen([sys.executable, str(script)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


PARA_EVERY = 3 * 3600      # 3시간에 한 번 뒤에서 정리한다


def para_autosort():
    """뒤에서 대화 줍기 — 세션 시작을 막지 않는다. LLM 은 안 부른다(collect --no-llm).
    판정(기록할지 · 어디로)은 사용자가 쓰는 AI 가 para-sort 스킬로 한다 — para_pending() 이 알린다."""
    st_path = HOME / "state" / "para-nudge.json"
    try:
        st = json.loads(st_path.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    now = time.time()
    collect = HOME / "para" / "collect.py"
    if now - st.get("collected", 0) < PARA_EVERY or not collect.is_file():
        return
    subprocess.Popen([sys.executable, str(collect), "--no-llm"], cwd=str(HOME), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    st["collected"] = now
    st_path.parent.mkdir(parents=True, exist_ok=True)
    st_path.write_text(json.dumps(st), encoding="utf-8")


def para_pending():
    """PARA 인박스에서 아직 정리 안 된 사건 수. 다른 대화가 정리 중이면 0."""
    try:
        lock = json.loads((HOME / "state" / "para-sort.lock").read_text(encoding="utf-8"))
        if time.time() - lock.get("at", 0) < 30 * 60:
            return 0
    except Exception:
        pass
    try:
        cfg = load_config(__file__)
        v, paths = pathlib.Path(cfg["vault"]).expanduser(), cfg.get("paths", {})
        inbox = (v / paths.get("para_inbox", "📥 PARA 인박스.md")).read_text(encoding="utf-8")
        hist_p = v / paths.get("para_history", "📤 PARA 이동 히스토리.md")
        done = set(re.findall(r"para-id: (\w+)", hist_p.read_text(encoding="utf-8"))) if hist_p.exists() else set()
    except Exception:
        return 0
    return len(set(re.findall(r"para-id: (\w+)", inbox)) - done)


# ── 대화 ↔ 프로젝트 (프롬프트 입력 때 LLM 없이 정한다) ─────────────
# 정한 값은 state/session-projects.json 에 둔다. 나중에 대화를 주울 때(collect) 이 값을 피쳐로 붙여
# 분류(classify)가 추측 없이 그 프로젝트로 보낸다. 기록은 여전히 일이 끝났을 때.
SP_FILE = HOME / "state" / "session-projects.json"
SKIP = {"미분류", "Daily"}                                 # 분류용 칸은 프로젝트로 정하지 않는다


def project_names():
    cfg = load_config(__file__)
    root = pathlib.Path(cfg["vault"]).expanduser() / cfg.get("paths", {}).get("projects", "1. Projects")
    import re as _re
    names = [_re.sub(r"^\d+\.\s*", "", d.name) for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")]
    return [n for n in names if n not in SKIP], pathlib.Path(cfg["vault"]).expanduser()


def guess_project(prompt, cwd, names, sp, prev, vault):
    """(프로젝트, 근거) 또는 (None, None). 프롬프트에 이름 > 같은 대화에서 앞서 정함 > 대화 폴더."""
    for n in sorted(names, key=len, reverse=True):          # 긴 이름 먼저 — "결제 개선 2차" 가 "결제" 보다 앞
        if len(n) >= 2 and n in prompt:
            return n, "프롬프트에 이름"
    if prev in names:
        return prev, "이 대화에서 앞서 정함"
    if cwd:
        try:
            prefs = json.loads((HOME / "state" / "todo-pile.json").read_text(encoding="utf-8"))
        except Exception:
            prefs = {}
        dirs = {path: proj for proj, path in (prefs.get("dirs") or {}).items() if proj in names}
        dirs.update({path: proj for path, proj in (sp.get("dirs") or {}).items() if proj in names})
        hits = [(len(path), proj) for path, proj in dirs.items() if cwd == path or cwd.startswith(path.rstrip("/") + "/")]
        if hits:
            return max(hits)[1], "대화 폴더"
    return None, None


def session_project(data, remind=False):
    """이 대화의 프로젝트를 정하고, 처음 정했거나 바뀌었을 때만 AI 에게 한 줄로 알린다.
    remind=True(세션 재개 · 압축 뒤)면 바뀌지 않았어도 다시 알린다 — 앞 대화 맥락이 사라졌을 수 있다."""
    sid = data.get("session_id")
    if not sid:
        return
    names, vault = project_names()
    try:
        sp = json.loads(SP_FILE.read_text(encoding="utf-8"))
    except Exception:
        sp = {}
    sessions = sp.setdefault("sessions", {})
    prev = (sessions.get(sid) or {}).get("project")
    cwd = (data.get("cwd") or "").rstrip("/")
    proj, how = guess_project(data.get("prompt") or "", cwd, names, sp, prev, vault)
    if not proj:
        return
    # 폴더를 배운다 — 이름으로 정했고, 홈 · vault · 이 프레임워크 폴더가 아니고, 아직 어느 프로젝트에도 안 묶인 폴더일 때만.
    # 이미 묶인 폴더에서 다른 프로젝트 이름이 지나가듯 나온 걸("결제 모듈처럼 …") 배우면 그 폴더가 영영 틀린다.
    plain = {str(pathlib.Path.home()), str(vault), str(HOME)}
    if how == "프롬프트에 이름" and cwd and cwd not in plain and not cwd.startswith(str(vault) + "/") \
            and guess_project("", cwd, names, sp, None, vault)[0] is None:
        sp.setdefault("dirs", {}).setdefault(cwd, proj)
    folder = guess_project("", cwd, names, sp, None, vault)[0]
    if proj == prev and how == "이 대화에서 앞서 정함":      # 처음 정한 근거를 남긴다 — 정리하는 AI 가 믿을지 판단한다
        how = (sessions.get(sid) or {}).get("how") or how
    sessions[sid] = {"project": proj, "how": how, "at": int(time.time())}
    if folder and folder != proj:
        sessions[sid]["folder"] = folder
    cutoff = time.time() - 14 * 86400                      # 2주 지난 대화는 지운다
    sp["sessions"] = {k: v for k, v in sessions.items() if v.get("at", 0) >= cutoff}
    SP_FILE.parent.mkdir(parents=True, exist_ok=True)
    SP_FILE.write_text(json.dumps(sp, ensure_ascii=False), encoding="utf-8")
    if proj != prev or remind:
        if folder and folder != proj:                      # 폴더와 이름이 다르다 — 이름이 지나가듯 나왔을 수 있다
            print("<para-project>이 대화: 프롬프트에 `%s` 이름이 나왔고, 작업 폴더는 `%s` 프로젝트다. 끝난 일을 기록할 때는 "
                  "실제로 고친 것 · 폴더가 어느 프로젝트 일인지 보고 고른다 (이름만 나온 거면 `%s`).</para-project>" % (proj, folder, folder))
        else:
            print("<para-project>이 대화의 프로젝트: `%s` (근거: %s). 끝난 일을 기록할 때(devlog · todo · tick) 이 프로젝트로 한다. "
                  "사용자가 다른 프로젝트 일이라고 하면 그쪽으로.</para-project>" % (proj, how))


def lint():
    cfg = load_config(__file__)
    vault = pathlib.Path(cfg["vault"]).expanduser()
    if not (vault / "1. Projects").is_dir():
        return []
    script = PLUGIN / "scripts" / "project_lint.py"       # 플러그인이 원본 — vault 에 스크립트가 없어도 돈다
    out = subprocess.run([sys.executable, str(script), "--json", "--vault", str(vault)],
                         capture_output=True, text=True, timeout=8).stdout
    return json.loads(out)


def lists():
    """영역(🧵 노트) · 자료 주제(폴더) 이름. 못 읽으면 빈 목록."""
    try:
        cfg = load_config(__file__)
        v, paths = pathlib.Path(cfg["vault"]).expanduser(), cfg.get("paths", {})
        a = sorted(p.stem.replace("🧵 ", "", 1) for p in (v / paths.get("areas", "2. Areas")).glob("🧵 *.md"))
        r = sorted(p.name for p in (v / paths.get("resources", "3. Resources")).iterdir() if p.is_dir() and not p.name.startswith("."))
        return (", ".join(a) or "(없음)"), (", ".join(r) or "(없음)")
    except Exception:
        return "(없음)", "(없음)"


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    if os.environ.get("MILLIE_PARA_LLM"):                  # 스크립트가 부른 claude -p — 훅 문구가 답을 오염시킨다
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    event = data.get("hook_event_name") or ("UserPromptSubmit" if data.get("prompt") else "SessionStart")
    try:
        session_project(data, remind=event == "SessionStart" and data.get("source") in ("resume", "compact", "clear"))
    except Exception:
        pass
    if event == "SessionStart":
        try:
            bootstrap()
        except Exception:
            pass
    rows = lint()
    bad = [r for r in rows if r["missing"]]

    if event == "SessionStart":
        record = PLUGIN / "scripts" / "vault_record.py"
        names = ", ".join(r["project"] for r in rows) or "(없음)"
        areas_s, topics_s = lists()
        print("## vault 실시간 기록\n\n"
              "작업 하나(기능·마일스톤·결정·이슈 해결)가 끝나 사용자에게 완료를 보고하는 **같은 턴**에 vault 에 기록한다. 다음 턴으로 미루지 않는다(미루면 사라진다).\n\n"
              "**기록할 가치가 있는 모든 프롬프트는 5곳(PARAS) 중 정확히 한 곳**에 들어간다:\n"
              "1. **Projects** — 끝이 있는 일(완료 조건·기한). `devlog` 한 줄 + 해당 항목이면 `tick`\n"
              "2. **Areas** — 끝이 없는 지속 책임(보안 점검·팀 운영 등). `area` 메모\n"
              "3. **Resources** — 나중에 찾아볼 참고 지식·자료·정책. `resource` 수집\n"
              "4. **Archives** — 끝난 것. 프로젝트가 완전히 끝났을 때만 `archive` (이동이라 승인 필요)\n"
              "5. **Store** — 임시로 밀린 것(나중에 다시 할 일). `shelve`(Projects→Store) / 다시 하게 되면 `resume` (둘 다 이동이라 승인 필요). Store 프로젝트에는 일지를 쓰지 않는다\n"
              "판정 순서: 끝이 있나 → Projects / 지속 책임 → Areas / 참고용 → Resources / 끝났나 → Archives / 지금은 못 하고 미룬다 → Store. 질문·잡담·탐색·진행 중 단계는 기록하지 않는다.\n\n"
              "**기한(날짜)이 있는 새 목표를 사용자가 말하면** 코드 작업이나 되묻기보다 먼저 `match --name <이름>` 으로 기존 프로젝트를 찾고, 없으면 등록을 제안한다. **새 프로젝트는 완료일(due) · 완료 조건 · 마일스톤(날짜)을 같이 물어 받아야 만들어진다** — 허락 질문에 이 셋을 한 번에 묻는다(`새 프로젝트 `<이름>` 만들까요? 완료일 / 완료 조건 / 마일스톤 날짜를 알려주세요`). 사용자가 말한 값만 쓰고 지어내지 않는다. 대상·방법이 모호해도 이 질문이 먼저다.\n\n"
              "**폴더·노트 생성은 사용자 허락 필요 (매번 만들지 않는다).** 맞는 곳을 찾는 순서: ① 기존에서 찾는다(`match --name <이름>`, 아래 목록) ② 정말 없을 때만 사용자에게 한 줄로 묻는다 — `새 <프로젝트|영역|자료 주제> `<이름>` 만들까요? (이유 한 줄)` ③ 답을 기다리는 동안은 `00. 미분류` 개발일지 로그에 `[분류 대기: 영역 보안] ...` 로 임시 기록 ④ 허락되면 영역·주제는 `new <area|topic> --name <이름> --approved`, 프로젝트는 `new project --name <이름> --due <YYYY-MM-DD> --done \"<완료 조건>\" --milestone \"<YYYY-MM-DD 내용>\" --approved` (셋이 없으면 스크립트가 거부한다. 사용자가 \"나중에\"라고 한 경우만 `--scope-later`) 후 기록, 거절되면 미분류 유지하고 같은 이름을 다시 묻지 않는다. `--approved` 는 사용자가 방금 허락했을 때만 붙인다.\n\n"
              "- 개발일지: `python3 %s devlog --project <이름> --section \"한 일\" --text \"...\"` (섹션: 한 일·결정·이슈·외부·로그)\n"
              "- 할 일: `... todo --project <이름> --text \"...\" --importance 상|중|하 --due YYYY-MM-DD --effort ⚡|🔸|🧱` — 받을 때 중요도·마감·난이도를 사용자에게 묻고 받은 값만 쓴다\n"
              "- 안 풀린 문제: `... issue --project <이름> --section \"프로젝트 이슈\" --text \"...\"` (프로젝트·정책·일정 이슈. 해결된 버그는 devlog `이슈` 섹션)\n"
              "- 항목 체크: `... tick --project <이름> --item \"<항목 일부>\"` (체크만. 날짜·문구는 고치지 않고 제안만)\n"
              "- 영역·자료: `... area --name <영역> --text ...` / `... resource --topic <주제> --text ...`\n"
              "- 현재 프로젝트: %s / 영역: %s / 자료 주제: %s\n기록 후 한 줄로만 보고한다.\n"
              % (record, names, areas_s, topics_s))
        try:
            para_autosort()
            n = para_pending()
        except Exception:
            n = 0
        if n:
            skill = PLUGIN / "skills" / "para-sort" / "SKILL.md"
            print("\n## PARA 정리 대기 %d건\n\n지난 AI 대화에서 주운 끝난 일이 정리를 기다린다. 이 세션 첫 응답 때 사용자 요청과 별개로 "
                  "Agent 도구를 `run_in_background: true` 로 한 번 띄워 정리를 맡긴다 — 프롬프트: "
                  "\"`%s` 를 읽고 그대로 따라 PARA 인박스를 정리한 뒤 결과를 한 줄로 보고\". 끝나면 그 한 줄을 사용자에게 전한다. "
                  "사용자가 정리를 원치 않는다고 하면 하지 않는다.\n" % (n, skill))
        if not bad:
            return

    if not bad:
        return

    if event == "SessionStart":
        # 이름을 접지 않는다 — "(외 N개)" 로 접으면 모델이 빈 곳을 추측으로 채운다
        groups = {}
        for r in bad:
            groups.setdefault(", ".join(r["missing"]), []).append(r["project"])
        lines = ["- 없음: %s — %s" % (miss, ", ".join(names)) for miss, names in groups.items()]
        ok = [r["project"] for r in rows if not r["missing"]]
        print("## 필수 항목이 빈 프로젝트 (%d개)\n\n프로젝트는 완료 조건 · 마일스톤(날짜) · 완료일이 있어야 한다. "
              "아래 프로젝트 작업·로그·회의가 나오면 한 줄로 채우자고 제안한다 (`/obsidian-project-scope <이름>`).\n\n%s\n\n"
              "채워짐: %s\n이 목록은 세션 시작 시점 기준이다. 비었다고 말하기 전에 `project_lint.py` 나 Overview 로 지금 상태를 확인한다."
              % (len(bad), "\n".join(lines), ", ".join(ok) or "(없음)"))
        return

    prompt = data.get("prompt") or ""
    sid = data.get("session_id") or "nosession"
    state = load_state()
    seen = set(state.get(sid, []))
    hit = [r for r in bad if r["project"] in prompt and r["project"] not in seen]
    if not hit:
        return
    for r in hit:
        seen.add(r["project"])
    state = {sid: sorted(seen)}             # 현재 세션만 유지 — 파일이 커지지 않는다
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    print("<project-guard>\n" + "\n".join(
        "프로젝트 `%s` 에 %s 이(가) 없다. 요청 처리와 함께 한 줄로 알리고 `/obsidian-project-scope %s` 로 채우자고 제안한다."
        % (r["project"], " · ".join(r["missing"]), r["project"]) for r in hit) + "\n</project-guard>")


try:
    main()
except Exception:
    sys.exit(0)
