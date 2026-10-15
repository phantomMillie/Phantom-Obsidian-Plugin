#!/usr/bin/env python3
"""프로젝트 필수 항목(완료 조건 · 마일스톤 · 완료일) 리마인드 훅.

  SessionStart      → 비어 있는 활성 프로젝트 요약 (최대 5개)
  UserPromptSubmit  → 프롬프트에 프로젝트 이름이 나오면, 그 프로젝트가 비었을 때 세션당 1번 상기

점검 로직은 플러그인의 `scripts/project_lint.py` (vault-init 이 vault `.scripts/` 에도 사본을 둔다).
vault·스크립트가 없거나 실패하면 아무것도 안 낸다 — 훅이 세션을 막지 않는다.
"""
import json
import pathlib
import subprocess
import sys

HOME = pathlib.Path(__file__).resolve().parent.parent
STATE = HOME / "state" / "guard.json"


def lint():
    cfg = json.loads((HOME / "config.json").read_text(encoding="utf-8"))
    vault = pathlib.Path(cfg["vault"]).expanduser()
    if not (vault / "1. Projects").is_dir():
        return []
    script = HOME / "scripts" / "project_lint.py"          # 플러그인이 원본 — vault 에 스크립트가 없어도 돈다
    out = subprocess.run([sys.executable, str(script), "--json", "--vault", str(vault)],
                         capture_output=True, text=True, timeout=8).stdout
    return json.loads(out)


def lists():
    """영역(🧵 노트) · 자료 주제(폴더) 이름. 못 읽으면 빈 목록."""
    try:
        cfg = json.loads((HOME / "config.json").read_text(encoding="utf-8"))
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
    rows = lint()
    bad = [r for r in rows if r["missing"]]

    if event == "SessionStart":
        record = HOME / "scripts" / "vault_record.py"
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
              "- 개발일지: `python3 %s devlog --project <이름> --section \"한 일\" --text \"...\"` (섹션: 한 일·결정·이슈·외부·내일·로그)\n"
              "- 항목 체크: `... tick --project <이름> --item \"<항목 일부>\"` (체크만. 날짜·문구는 고치지 않고 제안만)\n"
              "- 영역·자료: `... area --name <영역> --text ...` / `... resource --topic <주제> --text ...`\n"
              "- 현재 프로젝트: %s / 영역: %s / 자료 주제: %s\n기록 후 한 줄로만 보고한다.\n"
              % (record, names, areas_s, topics_s))
        if not bad:
            return

    if not bad:
        return

    if event == "SessionStart":
        lines = ["- %s — 없음: %s" % (r["project"], ", ".join(r["missing"])) for r in bad[:5]]
        more = "" if len(bad) <= 5 else "\n(외 %d개)" % (len(bad) - 5)
        print("## 필수 항목이 빈 프로젝트 (%d개)\n\n프로젝트는 완료 조건 · 마일스톤(날짜) · 완료일이 있어야 한다. "
              "아래 프로젝트 작업·로그·회의가 나오면 한 줄로 채우자고 제안한다 (`/obsidian-project-scope <이름>`).\n\n%s%s"
              % (len(bad), "\n".join(lines), more))
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
