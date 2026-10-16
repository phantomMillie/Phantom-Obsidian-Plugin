#!/usr/bin/env python3
"""프로젝트 필수 항목(완료 조건 · 마일스톤 · 완료일) 리마인드 훅.

  SessionStart      → 비어 있는 활성 프로젝트 전부 (빠진 항목별로 묶어 이름을 다 보인다)
  UserPromptSubmit  → 프롬프트에 프로젝트 이름이 나오면, 그 프로젝트가 비었을 때 세션당 1번 상기

SessionStart 때 scripts/bootstrap.py 도 부른다 — 플러그인만 받은 PC 에 vault · TODO 앱을 깐다.
점검 로직은 플러그인의 `scripts/project_lint.py` (vault-init 이 vault `.scripts/` 에도 사본을 둔다).
vault·스크립트가 없거나 실패하면 아무것도 안 낸다 — 훅이 세션을 막지 않는다.
"""
import json
import pathlib
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


PARA_EVERY = 3 * 3600      # 대화 줍기는 3시간에 한 번 (LLM 없이, 1~2초)
PARA_ASK_AT = 3            # 인박스에 이만큼 쌓이면 사용자에게 분류할지 묻는다


def para_pending():
    """뒤에서 AI 대화를 줍고(LLM 없음 — 끝 신호 있는 세션만), PARA 인박스에 쌓인 건수와 경로를 돌려준다.
    분류(LLM)는 여기서 돌리지 않는다 — 사용자에게 물어보고 승낙하면 그때."""
    collect = HOME / "para" / "collect.py"
    st_path = HOME / "state" / "para-nudge.json"
    try:
        st = json.loads(st_path.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    now = time.time()
    if collect.is_file() and now - st.get("collected", 0) > PARA_EVERY:
        subprocess.Popen([sys.executable, str(collect), "--no-llm"], cwd=str(HOME), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        st["collected"] = now
        st_path.parent.mkdir(parents=True, exist_ok=True)
        st_path.write_text(json.dumps(st), encoding="utf-8")
    cfg = load_config(__file__)
    inbox = pathlib.Path(cfg["vault"]).expanduser() / cfg.get("paths", {}).get("para_inbox", "📥 PARA 인박스.md")
    try:
        text = inbox.read_text(encoding="utf-8")
    except Exception:
        return 0, inbox, []
    titles = [ln[3:].strip() for ln in text.splitlines() if ln.startswith("## ")]
    return text.count("<!-- para-id:"), inbox, titles


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
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    event = data.get("hook_event_name") or ("UserPromptSubmit" if data.get("prompt") else "SessionStart")
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
              "- 항목 체크: `... tick --project <이름> --item \"<항목 일부>\"` (체크만. 날짜·문구는 고치지 않고 제안만)\n"
              "- 영역·자료: `... area --name <영역> --text ...` / `... resource --topic <주제> --text ...`\n"
              "- 현재 프로젝트: %s / 영역: %s / 자료 주제: %s\n기록 후 한 줄로만 보고한다.\n"
              % (record, names, areas_s, topics_s))
        try:
            n, inbox, titles = para_pending()
        except Exception:
            n, inbox, titles = 0, None, []
        if n >= PARA_ASK_AT and (HOME / "para" / "classify.py").is_file():
            ex = ", ".join("「%s」" % t[:30] for t in titles[:3])
            print("## vault 에 안 들어간 일 (%d건)\n\n"
                  "지난 AI 대화에서 끝난 일 %d건을 주워 PARA 인박스(`%s`)에 모아 뒀다. 아직 vault 의 제자리(프로젝트 개발일지 · 영역 · 자료)에는 안 들어갔다.\n"
                  "지금 넣지 않는다 — 먼저 묻는다. 이번 세션 첫 답 끝에, 무엇인지 알 수 있게 예시를 붙여 한 줄로:\n"
                  "`지난 대화에서 끝난 일 %d건이 아직 vault 에 정리 안 됐어요 — 예: %s. 프로젝트 개발일지 · 영역 · 자료 중 맞는 곳에 나눠 넣을까요?`\n"
                  "(그 답에 이미 다른 질문이 있으면 다음 답에서.) 승낙하면 `python3 %s --no-slack` 을 돌리고 어디로 몇 건 갔는지 한 줄로 알린다. "
                  "거절하면 이 세션에선 다시 묻지 않는다.\n"
                  % (n, n, inbox, n, ex or "(제목 없음)", HOME / "para" / "classify.py"))
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
