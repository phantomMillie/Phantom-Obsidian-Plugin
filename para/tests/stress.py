#!/usr/bin/env python3
"""PARA 정리 스트레스 테스트 — 가짜 vault · 가짜 AI 대화로 줍기 → 판정 → 기록 전 과정을 돌리고 채점한다.

  python3 para/tests/stress.py                      지금 코드, AI 판정(para-sort) 경로
  python3 para/tests/stress.py --path old           예전 경로 (collect --no-llm → classify LLM → vault 분배 배치)
  python3 para/tests/stress.py --code <dir>         다른 코드 사본으로 (para/ · plugin/ · vault-scripts/ 가 있는 폴더)
  python3 para/tests/stress.py --no-ai              판정(LLM) 없이 결정적 점검만
  python3 para/tests/stress.py --keep               샌드박스를 지우지 않는다

실제 vault · state · ~/.config 는 건드리지 않는다. 판정 AI 는 `claude -p --setting-sources project`
(훅 · 플러그인 없이 — 사용자가 쓰는 그 AI 를 대신한다). 대화 내용은 전부 지어낸 것이다.
"""
import argparse, datetime, json, os, pathlib, re, shutil, subprocess, sys, tempfile, time, uuid

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
REAL_HOME = pathlib.Path.home()
NOW = time.time()
TODAY = datetime.date.today()
FAKE = "/fake/code"
HOME_CWD = str(REAL_HOME)                       # 전역 대화 = 홈 폴더

PROJECTS = {"로그인 개선": f"{FAKE}/login-web", "결제": f"{FAKE}/pay-server", "뷰어 개선": f"{FAKE}/viewer-app",
            "배포 자동화": f"{FAKE}/infra", "Y": f"{FAKE}/y-app"}
AREAS = ["보안 점검"]
TOPICS = ["정책"]
VR = "python3 ~/.millie-obsidian/plugin/scripts/vault_record.py"
FAKE_KEY = "sk-" + "ant-" + "api03-" + "FAKE" * 3 + "1234567890abcdef"   # 가림 시험용 가짜 — 소스에 키 모양을 그대로 두지 않는다


# ── 대화 만들기 ─────────────────────────────────────────────────────
# 턴: ("u", 말) · ("a", 말, [("edit", 경로) | ("bash", 명령, 결과)])
def claude_jsonl(sid, cwd, title, turns, t0):
    out, ts = [{"type": "ai-title", "aiTitle": title, "sessionId": sid}], t0
    def base(kind):
        nonlocal ts
        ts += 30
        return {"type": kind, "sessionId": sid, "cwd": cwd, "entrypoint": "cli", "uuid": str(uuid.uuid4()),
                "timestamp": datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()}
    for t in turns:
        if t[0] == "u":
            out.append(dict(base("user"), message={"role": "user", "content": t[1]}))
            continue
        blocks, results = [{"type": "text", "text": t[1]}], []
        for tool in (t[2] if len(t) > 2 else []):
            tid = "toolu_" + uuid.uuid4().hex[:12]
            if tool[0] == "edit":
                blocks.append({"type": "tool_use", "id": tid, "name": "Edit", "input": {"file_path": tool[1], "old_string": "a", "new_string": "b"}})
                results.append({"type": "tool_result", "tool_use_id": tid, "content": "수정함"})
            else:
                blocks.append({"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": tool[1]}})
                results.append({"type": "tool_result", "tool_use_id": tid, "content": tool[2]})
        out.append(dict(base("assistant"), message={"role": "assistant", "content": blocks}))
        if results:
            out.append(dict(base("user"), message={"role": "user", "content": results}))
    return "\n".join(json.dumps(x, ensure_ascii=False) for x in out) + "\n"


def codex_jsonl(sid, cwd, turns, t0):
    out = [{"type": "session_meta", "timestamp": "", "payload": {"id": sid, "cwd": cwd, "source": "cli"}}]
    for t in turns:
        if t[0] == "u":
            out.append({"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": t[1]}]}})
            continue
        for tool in (t[2] if len(t) > 2 else []):
            if tool[0] == "edit":
                arg = f"*** Begin Patch\n*** Update File: {tool[1]}\n@@\n-a\n+b\n*** End Patch"
                out.append({"type": "response_item", "payload": {"type": "custom_tool_call", "name": "apply_patch", "input": arg}})
            else:
                out.append({"type": "response_item", "payload": {"type": "function_call", "name": "shell",
                                                                 "arguments": json.dumps({"command": ["bash", "-lc", tool[1]]})}})
        out.append({"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": t[1]}]}})
        out.append({"type": "event_msg", "payload": {"type": "task_complete"}})
    return "\n".join(json.dumps(x, ensure_ascii=False) for x in out) + "\n"


def gemini_new_jsonl(sid, turns, t0):
    msgs = [{"id": uuid.uuid4().hex[:8], "timestamp": "", "type": "user" if t[0] == "u" else "gemini",
             "content": [{"text": t[1]}]} for t in turns]
    lines = [{"sessionId": sid, "projectHash": "f" * 16, "startTime": "", "lastUpdated": "", "kind": "main"},
             {"$set": {"messages": msgs[:2], "lastUpdated": ""}}, {"$set": {"messages": msgs, "lastUpdated": ""}}]
    return "\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n"


# ── 케이스 ─────────────────────────────────────────────────────────
# expect: skip=True (기록 안 돼야 함) 또는 items=[{kind, target, sections?, issue?, todo?}]
#         extra: 파일 점검 (dedupe 등)
CASES = [
    dict(id="C01", name="잡담", tool="claude", cwd=HOME_CWD, title="러닝 앱 비유 문장", turns=[
        ("u", "러닝 기록 앱을 비유로 설명하는 문장 하나 만들어줘"),
        ("a", "\"러닝 앱은 발자국을 모아 지도를 그리는 일기장\" 어때?"),
        ("u", "하나만 더"), ("a", "\"매일의 숨을 선으로 남기는 앱\""),
        ("u", "오 좋네 ㄱㅅ"), ("a", "천만에!")],
        expect=dict(skip=True)),
    dict(id="C02", name="상태 확인 질문", tool="claude", cwd=PROJECTS["로그인 개선"], title="현재 작업 상태 확인", turns=[
        ("u", "지금 작업 상태 어떻게 돼?"),
        ("a", "git 상태 볼게", [("bash", "git status --short", " M src/LoginForm.tsx\n M src/api.ts")]),
        ("a", "브랜치 feat/login-a11y, 고친 파일 2개, 아직 커밋 안 함."),
        ("u", "ok 고마워"), ("a", "넵")],
        expect=dict(skip=True)),
    dict(id="C03", name="조회", tool="claude", cwd=PROJECTS["배포 자동화"], title="Actions 실행 목록", turns=[
        ("u", "GitHub Actions 최근 실행 목록 보여줘"),
        ("a", "조회할게", [("bash", "gh run list --limit 5", "completed success ci main\ncompleted failure ci main")]),
        ("a", "최근 5개 중 성공 4, 실패 1 (main ci)."),
        ("u", "확인 감사"), ("a", "넵")],
        expect=dict(skip=True)),
    dict(id="C04", name="진행 중(안 끝남)", tool="claude", cwd=PROJECTS["뷰어 개선"], title="목차 스크롤 튐", turns=[
        ("u", "목차 화면에서 스크롤이 튀는 거 고쳐줘"),
        ("a", "스크롤 위치를 보존하게 고쳤어", [("edit", f"{FAKE}/viewer-app/src/Toc.tsx")]),
        ("u", "아니 그거 말고, 가상 스크롤 높이 계산 쪽 문제 같아"),
        ("a", "가상 스크롤 행 높이 계산을 바꿨어. 다시 확인해줄래?", [("edit", f"{FAKE}/viewer-app/src/VirtualList.tsx")])],
        expect=dict(skip=True, allow_defer=True)),
    dict(id="C05", name="버그 수정 완료", tool="claude", cwd=PROJECTS["로그인 개선"], title="로그인 버튼 비활성 버그", turns=[
        ("u", "비밀번호를 입력해도 로그인 버튼이 계속 비활성인 버그 고쳐줘"),
        ("a", "원인: 비밀번호 onChange 가 state 를 안 바꿈. 고치고 커밋할게",
         [("edit", f"{FAKE}/login-web/src/LoginForm.tsx"), ("bash", "git commit -am 'fix: 로그인 버튼 활성 조건'", "[main 1a2b3c] fix")]),
        ("u", "됐다"), ("a", "굿")],
        expect=dict(items=[dict(kind="project", target="로그인 개선", sections={"한 일", "이슈"}, issue=False)])),
    dict(id="C06", name="결정", tool="claude", cwd=PROJECTS["결제"], title="환불 기간 정책", turns=[
        ("u", "환불 기간을 7일로 할지 14일로 할지 비교해줘"),
        ("a", "7일: 악용 적음, 문의 많음 / 14일: 만족도 높음, 정산 늦어짐"),
        ("u", "7일로 정하자. 문서에도 반영해"),
        ("a", "환불은 결제 후 7일 이내로 결정, 문서 반영함", [("edit", f"{FAKE}/pay-server/docs/refund.md")]),
        ("u", "ㅇㅋ 끝"), ("a", "넵")],
        expect=dict(items=[dict(kind="project", target="결제", sections={"결정"})])),
    dict(id="C07", name="일부 해결 + 남은 문제", tool="claude", cwd=PROJECTS["뷰어 개선"], title="책 열 때 크래시", turns=[
        ("u", "책 열 때 앱이 죽는 거 고쳐줘"),
        ("a", "iOS 원인은 폰트 캐시가 nil 일 때 강제 언래핑. 고쳤어. 안드로이드 같은 증상은 재현이 안 돼서 못 봤어",
         [("edit", f"{FAKE}/viewer-app/ios/Reader.swift")]),
        ("u", "일단 iOS 만 커밋하고 안드로이드는 다음에 로그 받아서 보자"),
        ("a", "iOS 만 커밋함. 안드로이드는 크래시 로그가 있어야 볼 수 있어",
         [("bash", "git commit -am 'fix: iOS 책 열기 크래시'", "[main 9f8e7d] fix")]),
        ("u", "ㅇㅇ 고마워"), ("a", "넵")],
        expect=dict(items=[dict(kind="project", target="뷰어 개선", issue=True, todo=True)])),
    dict(id="C08", name="영역(지속 책임)", tool="claude", cwd=HOME_CWD, title="월간 보안 점검", turns=[
        ("u", "이번 달 정기 보안 점검이야. 의존성 취약점 스캔 돌리고 high 있으면 올려줘"),
        ("a", "스캔 돌릴게", [("bash", "npm audit --audit-level=high", "2 high severity vulnerabilities")]),
        ("a", "high 2개(lodash, minimist) 버전 올렸고 다시 스캔하니 0개", [("edit", f"{HOME_CWD}/tools/package.json")]),
        ("u", "됐다 고마워"), ("a", "넵")],
        expect=dict(items=[dict(kind="area", target="보안 점검")])),
    dict(id="C09", name="자료(참고용)", tool="claude", cwd=HOME_CWD, title="쿠키 동의 요건", turns=[
        ("u", "쿠키 동의 배너 법적 요건 정리해줘. 나중에 참고하려고"),
        ("a", "정리: 1) 필수·선택 쿠키 구분 2) 거부 버튼을 동의만큼 쉽게 3) 동의 기록 보관 4) 언제든 철회 가능"),
        ("u", "철회는 어디서 해야 해?"), ("a", "설정 화면이나 푸터 링크처럼 늘 닿는 곳"),
        ("u", "좋아 고마워 참고할게"), ("a", "넵")],
        expect=dict(items=[dict(kind="resource", target="정책")])),
    dict(id="C10", name="다른 프로젝트 이름이 지나가듯 나옴", tool="claude", cwd=PROJECTS["Y"], title="프로필 화면 README", turns=[
        ("u", "결제 모듈 README 처럼 프로필 화면 README 도 정리해줘"),
        ("a", "프로필 화면 README 를 구조 · 상태 · API 로 정리했어", [("edit", f"{FAKE}/y-app/docs/profile.md")]),
        ("u", "굿 됐어"), ("a", "넵")],
        expect=dict(items=[dict(kind="project", target="Y")])),
    dict(id="C11", name="한 대화에 두 프로젝트", tool="claude", cwd=HOME_CWD, title="비번 찾기 링크 · CI 캐시", turns=[
        ("u", "로그인 개선 건: 비밀번호 찾기 링크가 404 야, 고쳐줘"),
        ("a", "링크 경로 고치고 커밋함", [("edit", f"{FAKE}/login-web/src/Find.tsx"), ("bash", "git -C /fake/code/login-web commit -am 'fix: 비번 찾기 링크'", "[main 111] fix")]),
        ("u", "됐다. 이제 배포 자동화 쪽 — CI 캐시 키가 잘못돼서 매번 풀빌드야, 고쳐줘"),
        ("a", "캐시 키를 lockfile 해시로 바꾸고 커밋함", [("edit", f"{FAKE}/infra/.github/workflows/ci.yml"), ("bash", "git -C /fake/code/infra commit -am 'fix: CI 캐시 키'", "[main 222] fix")]),
        ("u", "굿 끝"), ("a", "넵")],
        expect=dict(items=[dict(kind="project", target="로그인 개선"), dict(kind="project", target="배포 자동화")])),
    dict(id="C12", name="Codex 대화", tool="codex", cwd=PROJECTS["배포 자동화"], title="", turns=[
        ("u", "배포 스크립트에 롤백 옵션 추가해줘"),
        ("a", "deploy.sh 에 --rollback 옵션 추가함 (직전 태그로 되돌림)", [("edit", "scripts/deploy.sh")]),
        ("u", "좋아 됐다"), ("a", "넵")],
        expect=dict(items=[dict(kind="project", target="배포 자동화")])),
    dict(id="C13", name="Gemini 새 형식", tool="gemini", cwd="", title="", turns=[
        ("u", "결제 영수증 메일 템플릿에 부가세 줄이 빠졌어, 추가해줘"),
        ("a", "영수증 메일 템플릿에 부가세 줄 추가함"),
        ("u", "결제 쪽 그거 됐다 고마워"), ("a", "넵")],
        expect=dict(items=[dict(kind="project", target="결제")])),
    dict(id="C14", name="30시간 전 대화(주말 공백)", tool="claude", cwd=PROJECTS["로그인 개선"], title="다크모드 대비", age_h=30, turns=[
        ("u", "로그인 화면 다크모드에서 안내 문구 대비가 낮아, 고쳐줘"),
        ("a", "문구 색을 대비 4.5:1 이상으로 바꾸고 커밋함", [("edit", f"{FAKE}/login-web/src/theme.ts"), ("bash", "git commit -am 'fix: 다크모드 대비'", "[main 333] fix")]),
        ("u", "됐다"), ("a", "굿")],
        expect=dict(items=[dict(kind="project", target="로그인 개선")])),
    dict(id="C15", name="이미 바로 기록함(개발일지)", tool="claude", cwd=PROJECTS["로그인 개선"], title="실패 메시지 문구",
         realtime=["devlog", "--project", "로그인 개선", "--section", "한 일", "--text", "로그인 실패 메시지 문구를 '아이디 또는 비밀번호 확인' 으로 변경"],
         turns=[
        ("u", "로그인 실패 메시지 문구를 '아이디 또는 비밀번호 확인' 으로 바꿔줘"),
        ("a", "바꿨어", [("edit", f"{FAKE}/login-web/src/messages.ts"),
                       ("bash", f'{VR} devlog --project "로그인 개선" --section "한 일" --text "로그인 실패 메시지 문구를 \'아이디 또는 비밀번호 확인\' 으로 변경"',
                        "기록 로그인 개선 ▸ today.md ▸ 한 일")]),
        ("a", "기록: 로그인 개선 ▸ 한 일"),
        ("u", "됐다"), ("a", "굿")],
        expect=dict(dedupe=("devlog", "로그인 개선", "실패 메시지"))),
    dict(id="C16", name="이미 바로 기록함(할 일)", tool="claude", cwd=PROJECTS["결제"], title="할 일 추가",
         realtime=["todo", "--project", "결제", "--text", "결제 실패 알림 슬랙 연동 검토", "--importance", "중",
                   "--due", (TODAY + datetime.timedelta(days=7)).isoformat(), "--effort", "🔸"],
         turns=[
        ("u", "할 일 하나 넣어줘: 결제 실패 알림 슬랙 연동 검토. 중요도 중, 마감 다음 주, 반나절"),
        ("a", "넣었어", [("bash", f'{VR} todo --project "결제" --text "결제 실패 알림 슬랙 연동 검토" --importance 중 --due 2026-10-23 --effort 🔸',
                        "할 일 결제 ▸ today.md ▸ 중요도 중")]),
        ("u", "ㄱㅅ"), ("a", "넵"), ("u", "끝"), ("a", "넵")],
        expect=dict(dedupe=("todo", "결제", "실패 알림"))),
    dict(id="C17", name="한 대화에 같은 프로젝트 일 두 개", tool="claude", cwd=PROJECTS["결제"], title="웹훅 서명 · 정산 CSV", turns=[
        ("u", "결제 웹훅에 서명 검증 추가해줘"),
        ("a", "HMAC 서명 검증 추가하고 커밋함", [("edit", f"{FAKE}/pay-server/src/webhook.ts"), ("bash", "git commit -am 'feat: 웹훅 서명 검증'", "[main 444] feat")]),
        ("u", "됐다. 하나 더 — 정산 리포트 CSV 컬럼 순서를 날짜 먼저로 바꿔줘"),
        ("a", "CSV 컬럼 순서 바꾸고 커밋함", [("edit", f"{FAKE}/pay-server/src/report.ts"), ("bash", "git commit -am 'fix: 정산 CSV 컬럼 순서'", "[main 555] fix")]),
        ("u", "끝 고마워"), ("a", "넵")],
        expect=dict(items=[dict(kind="project", target="결제")], mentions=("결제", ["서명", "CSV"]))),
    dict(id="C18", name="비밀값이 섞인 대화", tool="claude", cwd=PROJECTS["배포 자동화"], title="배포 키 교체", turns=[
        ("u", f"배포 워크플로 시크릿 이름을 DEPLOY_TOKEN 으로 바꿔줘. 지금 값은 {FAKE_KEY} 야"),
        ("a", "워크플로에서 시크릿 이름을 DEPLOY_TOKEN 으로 바꿨어. 값은 저장소 시크릿에 넣어야 해 (커밋 안 함)", [("edit", f"{FAKE}/infra/.github/workflows/deploy.yml")]),
        ("u", "됐다"), ("a", "굿")],
        expect=dict(items=[dict(kind="project", target="배포 자동화")], secret=FAKE_KEY[:14])),
    dict(id="C19", name="새 영역이 필요한 일", tool="claude", cwd=HOME_CWD, title="분기 온보딩 문서", turns=[
        ("u", "분기마다 하는 신규 입사자 온보딩 체크리스트 이번 분기 것으로 갱신해줘"),
        ("a", "온보딩 체크리스트에 이번 분기 계정 · 장비 항목을 갱신했어", [("edit", f"{HOME_CWD}/docs/onboarding.md")]),
        ("u", "됐어 고마워"), ("a", "넵")],
        expect=dict(new_area=True)),
    dict(id="C20", name="긴 대화 중간에 끝난 일", tool="claude", cwd=PROJECTS["뷰어 개선"], title="이것저것", turns=[
        ("u", "오늘 날씨 좋네"), ("a", "그러게요"), ("u", "주말에 뭐 해?"), ("a", "저는 쉬어요"), ("u", "커피 추천해줘"), ("a", "라떼요"),
        ("u", "하이라이트 색이 다크모드에서 안 보여, 고쳐줘"),
        ("a", "하이라이트 색을 다크모드용으로 따로 두고 커밋함", [("edit", f"{FAKE}/viewer-app/src/highlight.ts"), ("bash", "git commit -am 'fix: 다크모드 하이라이트 색'", "[main 666] fix")]),
        ("u", "됐다")] + [x for k in range(14) for x in (("u", f"잡담 {k}: 점심 뭐 먹지"), ("a", f"글쎄요 {k}"))] + [("u", "ㅋㅋ 고마워"), ("a", "넵")],
        expect=dict(items=[dict(kind="project", target="뷰어 개선")])),
    dict(id="C21", name="사용자가 프로젝트를 직접 정정", tool="claude", cwd=PROJECTS["Y"], title="공용 결제 위젯", turns=[
        ("u", "공용 결제 위젯 버튼 문구를 '결제하기' 로 바꿔줘"),
        ("a", "버튼 문구 바꿨어", [("edit", f"{FAKE}/y-app/src/shared/PayButton.tsx")]),
        ("u", "참고로 이거 Y 일 아니고 결제 프로젝트 일이야. 됐어"), ("a", "알겠어, 결제 쪽 일로 볼게")],
        expect=dict(items=[dict(kind="project", target="결제")])),
]


def vary(c, k):
    tag = f"모듈{chr(65 + k)}"
    def t(x):
        return f"{x} ({tag})"
    turns = [(x[0], t(x[1]), *x[2:]) for x in c["turns"]]
    out = dict(c, id=c["id"] + (f"·{k + 1}" if k else ""), turns=turns, title=c["title"] and f"{c['title']} {tag}", tag=tag)
    if c.get("realtime"):
        rt = list(c["realtime"])
        rt[rt.index("--text") + 1] = t(rt[rt.index("--text") + 1])
        out["realtime"] = rt
    return out


# ── 샌드박스 ───────────────────────────────────────────────────────
def sh(cmd, env=None, cwd=None, stdin=None, timeout=900):
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=e, cwd=cwd, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def build(S, code):
    """S 아래 vault · 코드 사본 · 가짜 대화 · 설정."""
    shutil.copytree(REPO / "plugin" / "vault-template", S / "vault")
    shutil.copytree(code / "para", S / "para", ignore=shutil.ignore_patterns("tests", "__pycache__"))
    shutil.copytree(code / "plugin", S / "plugin", ignore=shutil.ignore_patterns("__pycache__", "tools"))
    vs = code / "vault-scripts"
    if vs.is_dir():
        (S / "vault" / ".scripts").mkdir(exist_ok=True)
        for f in vs.iterdir():
            shutil.copy2(f, S / "vault" / ".scripts" / f.name)
        (S / "vault" / ".scripts" / "devlog_rules.json").write_text(json.dumps({"projects": {}, "sections": {}}), encoding="utf-8")
        (S / "vault" / ".scripts" / "issue_rules.json").write_text(json.dumps({"sections": {}}), encoding="utf-8")
    cfg = json.loads((REPO / "config.example.json").read_text(encoding="utf-8"))
    cfg["vault"] = str(S / "vault")
    cfg["paths"]["keyword_rules"] = ".scripts/devlog_rules.json"
    cfg.setdefault("classify", {})["fallback_project"] = "미분류"
    cfg["local"] = {"anthropic_key": str(S / "no-key"), "llm_cmd": str(S / "llm-cmd"), "slack_webhook": str(S / "no-webhook")}
    (S / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    (S / "llm-cmd").write_text("claude -p --setting-sources project\n")
    env = {"MILLIE_HOME": str(S), "MILLIE_VAULT": str(S / "vault")}
    vr = [sys.executable, str(S / "plugin" / "scripts" / "vault_record.py")]
    due = (TODAY + datetime.timedelta(days=60)).isoformat()
    for p in PROJECTS:
        rc, out, err = sh(vr + ["new", "project", "--name", p, "--due", due, "--done", "출시", "--milestone", f"{due} 출시", "--approved"], env)
        assert rc == 0, err
    for a in AREAS:
        assert sh(vr + ["new", "area", "--name", a, "--approved"], env)[0] == 0
    for t in TOPICS:
        assert sh(vr + ["new", "topic", "--name", t, "--approved"], env)[0] == 0
    (S / "state").mkdir(exist_ok=True)
    # 세션 시작 훅을 시험할 때 진짜 설치(bootstrap) · 진짜 대화 줍기가 돌지 않게
    (S / "plugin" / "scripts" / "bootstrap.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    (S / "state" / "para-nudge.json").write_text(json.dumps({"collected": NOW}), encoding="utf-8")
    (S / "state" / "todo-pile.json").write_text(json.dumps({"dirs": PROJECTS}, ensure_ascii=False), encoding="utf-8")
    # 지난 정리는 40시간 전 — 그 뒤 30시간 전에 끝난 대화(C14)도 주워야 한다
    (S / "state" / "collect.json").write_text(json.dumps({"sessions": {}, "last_run": NOW - 40 * 3600}), encoding="utf-8")
    (S / "home" / ".config").mkdir(parents=True)
    return env, vr


def write_sources(S, env, vr):
    src = S / "src"
    meta = {}
    for i, c in enumerate(CASES):
        sid = str(uuid.UUID(int=i + 1))
        mtime = NOW - c.get("age_h", 1) * 3600
        t0 = mtime - 600
        if c["tool"] == "claude":
            d = src / ".claude" / "projects" / ("-" + re.sub(r"[^A-Za-z0-9]", "-", c["cwd"]).strip("-"))
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"{sid}.jsonl"
            p.write_text(claude_jsonl(sid, c["cwd"], c["title"], c["turns"], t0), encoding="utf-8")
            for t in c["turns"]:                         # 프롬프트 입력 훅 — 운영과 같은 스크립트를 그대로
                if t[0] == "u":
                    sh([sys.executable, str(S / "plugin" / "hooks" / "project_guard.py")], env,
                       stdin=json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": sid, "cwd": c["cwd"], "prompt": t[1]}))
        elif c["tool"] == "codex":
            d = src / ".codex" / "sessions" / f"{TODAY:%Y/%m/%d}"
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"rollout-{TODAY:%Y-%m-%d}T00-00-00-{sid}.jsonl"
            p.write_text(codex_jsonl(sid, c["cwd"], c["turns"], t0), encoding="utf-8")
        else:
            d = src / ".gemini" / "tmp" / "fake-proj" / "chats"
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"session-{TODAY:%Y-%m-%d}T00-00-{sid}.jsonl"
            p.write_text(gemini_new_jsonl(sid, c["turns"], t0), encoding="utf-8")
        os.utime(p, (mtime, mtime))
        if c.get("realtime"):
            rc, out, err = sh(vr + c["realtime"], env)
            assert rc == 0, err
        meta[str(p)] = c["id"]
    return meta


# ── 실행 ───────────────────────────────────────────────────────────
def run_collect(S, args=()):
    return sh([sys.executable, str(S / "para" / "collect.py"), *args], {"HOME": str(S / "src"), "MILLIE_HOME": str(S)})


def inbox_ids(S):
    """PARA 인박스 블록 para-id → 대화 경로."""
    t = (S / "vault" / "📥 PARA 인박스.md").read_text(encoding="utf-8") if (S / "vault" / "📥 PARA 인박스.md").exists() else ""
    out = {}
    for m in re.finditer(r"^- 기록: `([^`]+)`.*?$.*?^<!-- para-id: (\w+) -->", t, re.S | re.M):
        out[m.group(2)] = m.group(1)
    return out


def ai_judge(S, pending_text):
    """사용자가 쓰는 AI 를 대신해 판정 — para-sort 스킬 본문 + --pending 출력."""
    skill = (S / "plugin" / "skills" / "para-sort" / "SKILL.md").read_text(encoding="utf-8")
    skill = re.sub(r"^---.*?---\n", "", skill, flags=re.S)
    prompt = (skill + "\n\n---\n지금은 시험이다. 명령을 실행하거나 파일을 쓰지 말고, `--apply` 에 넣을 판정 JSON 만 출력하라.\n"
              "아래가 `classify.py --pending` 출력이다.\n\n" + pending_text)
    rc, out, err = sh(["claude", "-p", "--setting-sources", "project"], cwd=str(S), stdin=prompt, timeout=900)
    if rc != 0:
        raise RuntimeError("판정 AI 실패: " + (err or out)[:300])
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        raise RuntimeError("판정 JSON 없음: " + out[:300])
    return json.loads(m.group(0))


def pipeline_ai(S, log):
    rc, out, err = run_collect(S, ["--no-llm"])
    log("collect", rc, out + err)
    ids = inbox_ids(S)
    py = [sys.executable, str(S / "para" / "classify.py")]
    rc, pend, err = sh(py + ["--pending", "--claim"], {"MILLIE_HOME": str(S)})
    log("pending", rc, pend[-3000:] + err)
    if rc != 0:
        return ids, f"--pending 실패 rc={rc}"
    verdict = ai_judge(S, pend)
    (S / "verdict.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=1), encoding="utf-8")
    rc, out, err = sh(py + ["--apply", str(S / "verdict.json")], {"MILLIE_HOME": str(S)})
    log("apply", rc, out + err)
    return ids, None if rc == 0 else f"--apply 실패 rc={rc}: {err[-300:]}"


def pipeline_old(S, log):
    rc, out, err = run_collect(S, ["--no-llm"])
    log("collect", rc, out + err)
    ids = inbox_ids(S)
    rc, out, err = sh([sys.executable, str(S / "para" / "classify.py"), "--no-slack"], {"MILLIE_HOME": str(S)})
    log("classify", rc, out + err)
    for script in ("devlog_dispatch.py", "issue_dispatch.py"):
        f = S / "vault" / ".scripts" / script
        if f.exists():
            rc, out, err = sh([sys.executable, str(f), "--no-llm", "--no-slack"], {"HOME": str(S / "home")}, cwd=str(S / "vault"))
            log(script, rc, out + err)
    return ids, None


# ── 채점 ───────────────────────────────────────────────────────────
HIST_ROW = re.compile(r"^- (?P<title>.+?) → (?P<dest>.+) · (?P<how>[^·]+?) <!-- para-id: (?P<id>\w+) -->", re.M)


def parse_dest(d):
    out = []
    for part in re.split(r" \+ ", d):
        m = re.match(r"\[\[1\. Projects/[^|]*\|([^\]]+)\]\](?: \((.*)\))?", part)
        if m:
            parts = (m.group(2) or "").split(" · ")       # 개발일지 · <섹션> · 이슈 · 할 일 N
            out.append(dict(kind="project", target=m.group(1), sections=set(parts[1:2]),
                            issue="이슈" in parts[2:], todo=any(x.startswith("할 일") for x in parts[2:])))
            continue
        m = re.search(r"🧵 ([^\]|(]+?)(?:\]\]| 승인 대기|$)", part)
        if m:
            out.append(dict(kind="area", target=m.group(1).strip()))
            continue
        m = re.search(r"📎 ([^\]|]+?)\]\]", part)
        if m:
            out.append(dict(kind="resource", target=m.group(1).strip()))
            continue
        out.append(dict(kind="skip", target=part))
    return out


def files_text(S, kind, project):
    v = S / "vault"
    if kind == "devlog":
        d = v / "3. Resources" / "03. 개발일지" / f"{project} 개발일지"
        return "\n".join(p.read_text(encoding="utf-8") for p in d.glob("*.md")) if d.exists() else ""
    d = v / "3. Resources" / "07. TODO"
    return "\n".join(p.read_text(encoding="utf-8") for p in d.glob("*.md")) if d.exists() else ""


def score(S, path_ids, convo_case):
    hist = (S / "vault" / "📤 PARA 이동 히스토리.md")
    rows = [m.groupdict() for m in HIST_ROW.finditer(hist.read_text(encoding="utf-8"))] if hist.exists() else []
    inbox_left = inbox_ids(S)
    got = {c["id"]: [] for c in CASES}
    collected = {c["id"]: False for c in CASES}
    for pid, path in path_ids.items():
        cid = convo_case.get(path)
        if cid:
            collected[cid] = True
    for r in rows:
        cid = convo_case.get(path_ids.get(r["id"], ""))
        if cid:
            got[cid] += [dict(x, how=r["how"].strip()) for x in parse_dest(r["dest"])]
    left = {convo_case.get(p) for p in inbox_left.values()}
    results = []
    for c in CASES:
        e, g = c["expect"], [x for x in got[c["id"]] if x["kind"] != "skip"]
        why = []
        if e.get("dedupe"):
            kind, proj, word = e["dedupe"]
            n = sum(1 for l in files_text(S, kind, proj).splitlines() if word in l and c.get("tag", "") in l)
            if n != 1:
                why.append(f"{'개발일지' if kind == 'devlog' else 'TODO'}에 '{word}' {n}번 (1번이어야)")
        elif e.get("new_area"):
            made = sorted(p.stem for p in (S / "vault" / "2. Areas").glob("🧵 *.md") if p.stem.replace("🧵 ", "") not in AREAS)
            if made:
                why.append("승인 없이 영역을 만듦: " + ", ".join(made))
            blk = [b for b in re.split(r"\n(?=## )", (S / "vault" / "📥 PARA 인박스.md").read_text(encoding="utf-8")) if any(path_ids.get(i) and convo_case.get(path_ids[i]) == c["id"] for i in re.findall(r"para-id: (\w+)", b))]
            if not any("영역 만들기" in b for b in blk):
                why.append("승인 체크박스 없음 (실제: " + (", ".join(f"{x['kind']}:{x['target']}" for x in g) or "인박스에 그냥 남음") + ")")
        elif e.get("skip"):
            if g:
                why.append("기록됨: " + ", ".join(f"{x['kind']}:{x['target']}" for x in g))
            if c["id"] in left and not e.get("allow_defer"):
                why.append("인박스에 남음")
        else:
            if not collected[c["id"]]:
                why.append("수집 안 됨")
            for want in e["items"]:
                hit = [x for x in g if x["kind"] == want["kind"] and x["target"] == want["target"]]
                if not hit:
                    why.append(f"없음 {want['kind']}:{want['target']} (실제: {', '.join(x['kind'] + ':' + x['target'] for x in g) or '없음'})")
                    continue
                if want.get("sections") and not any(x.get("sections", set()) & want["sections"] for x in hit):
                    why.append(f"섹션 {'/'.join(sorted(want['sections']))} 아님 ({', '.join('/'.join(sorted(x.get('sections', []))) for x in hit)})")
                for k in ("issue", "todo"):
                    if k in want and any(x.get(k) for x in hit) != want[k]:
                        why.append(f"{'이슈' if k == 'issue' else '할 일'} {'있어야' if want[k] else '없어야'}")
            extra = [x for x in g if not any(x["kind"] == w["kind"] and x["target"] == w["target"] for w in e["items"])]
            if extra:
                why.append("엉뚱한 곳: " + ", ".join(f"{x['kind']}:{x['target']}" for x in extra))
            if e.get("mentions"):
                proj, words = e["mentions"]
                t = files_text(S, "devlog", proj)
                miss = [w for w in words if w not in t]
                if miss:
                    why.append(f"{proj} 개발일지에 빠짐: {', '.join(miss)}")
        if e.get("secret"):
            leak = [str(p.relative_to(S / "vault")) for p in (S / "vault").rglob("*.md") if e["secret"] in p.read_text(encoding="utf-8", errors="ignore")]
            if leak:
                why.append("비밀값이 남음: " + ", ".join(leak))
        results.append((c["id"], c["name"], not why, "; ".join(why)))
    return results


# ── 결정적 점검 (LLM 없음) ────────────────────────────────────────
def checks(S, env, mode):
    out = []
    pg = [sys.executable, str(S / "plugin" / "hooks" / "project_guard.py")]
    sp = S / "state" / "session-projects.json"
    # 폴더가 이미 Y 인데 프롬프트에 다른 프로젝트 이름이 지나가면 폴더를 그 프로젝트로 배우면 안 된다
    learned = json.loads(sp.read_text(encoding="utf-8")).get("dirs", {}) if sp.exists() else {}
    bad = {k: v for k, v in learned.items() if k in PROJECTS.values() and v != next(p for p, d in PROJECTS.items() if d == k)}
    out.append(("D1", "이미 연결된 폴더를 다른 프로젝트로 배우지 않음", not bad, f"잘못 배움: {bad}" if bad else ""))
    # 판정용 LLM 호출(claude -p)에서 훅이 돌면 안 된다 — 답이 훅 문구로 오염된다
    before = sp.read_text(encoding="utf-8") if sp.exists() else ""
    rc, o, e = sh(pg, dict(env, MILLIE_PARA_LLM="1"), stdin=json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "llm-call", "cwd": HOME_CWD, "prompt": "결제 로그인 개선"}))
    after = sp.read_text(encoding="utf-8") if sp.exists() else ""
    out.append(("D2", "스크립트가 부른 claude -p 에선 훅이 조용", not o.strip() and before == after, (o.strip()[:80] or "state 바뀜") if (o.strip() or before != after) else ""))
    # 정리 결과가 인박스에만 머물지 않고 실제 개발일지 파일까지 가야 한다 (분배 배치가 없는 새 vault 포함)
    hist = S / "vault" / "📤 PARA 이동 히스토리.md"
    projs = set(re.findall(r"\[\[1\. Projects/[^|]*\|([^\]]+)\]\]", hist.read_text(encoding="utf-8"))) if hist.exists() else set()
    empty = sorted(p for p in projs if p in PROJECTS and not files_text(S, "devlog", p).count(f"{TODAY:%Y-%m-%d}"))
    has_dispatch = (S / "vault" / ".scripts" / "devlog_dispatch.py").exists()
    out.append(("D3", "정리 결과가 개발일지 파일까지 감" + ("" if has_dispatch else " (vault 분배 배치 없음)"), bool(projs) and not empty,
                ("개발일지 비어 있음: " + ", ".join(empty)) if empty else ("" if projs else "프로젝트로 간 게 없음")))
    # 폴더는 Y 인데 프롬프트에 결제 이름 — 바로 기록하는 AI 에게 둘 다 알려야 한다
    rc, o, e = sh(pg, env, stdin=json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "d6", "cwd": PROJECTS["Y"], "prompt": "결제 모듈 문서처럼 이것도 정리해줘"}))
    out.append(("D6", "폴더와 이름이 다르면 바로 기록하는 AI 에게 둘 다 알림", "`Y`" in o and "`결제`" in o, o.strip()[:120]))
    return out


def check_session_start(S, env):
    """세션 시작: 대기가 있으면 백그라운드 정리를 지시, 잠금 중이면 조용."""
    pg = [sys.executable, str(S / "plugin" / "hooks" / "project_guard.py")]
    ev = json.dumps({"hook_event_name": "SessionStart", "source": "startup", "session_id": "d7", "cwd": HOME_CWD})
    o1 = sh(pg, env, stdin=ev)[1]
    lock = S / "state" / "para-sort.lock"
    lock.write_text(json.dumps({"at": time.time()}), encoding="utf-8")
    o2 = sh(pg, env, stdin=ev)[1]
    lock.unlink()
    good = "PARA 정리 대기" in o1 and "run_in_background" in o1 and "PARA 정리 대기" not in o2
    return [("D7", "세션 시작: 대기 있으면 백그라운드 정리 지시 · 잠금 중엔 조용", good,
             "" if good else f"대기 알림={'PARA 정리 대기' in o1}, 잠금 중 알림={'PARA 정리 대기' in o2}")]


def check_lock_and_race(S):
    """--claim 잠금 · --apply 도중 새로 쌓인 사건 보존 · 판정 없는 id 보존 (AI 경로만)."""
    out = []
    py = [sys.executable, str(S / "para" / "classify.py")]
    env = {"MILLIE_HOME": str(S)}
    inbox = S / "vault" / "📥 PARA 인박스.md"
    t = inbox.read_text(encoding="utf-8")
    block = "\n\n## 경합 시험 사건\n- 도구: Claude Code\n- 기록: `/fake/race.jsonl` (턴 0–3)\n- 피쳐: —\n- 종료: 작업 완료 · 끝 신호: 사용자 말\n- 요약: 경합 시험\n- 수집: 2026-01-01 00:00\n<!-- para-id: race00000001 -->\n"
    inbox.write_text(t.rstrip("\n") + block, encoding="utf-8")
    rc1 = sh(py + ["--pending", "--claim"], env)[0]
    rc2 = sh(py + ["--pending", "--claim"], env)[0]
    out.append(("D4", "두 대화가 동시에 정리하지 않음(잠금)", rc1 == 0 and rc2 != 0, f"첫 claim rc={rc1}, 두 번째 rc={rc2}"))
    (S / "empty.json").write_text(json.dumps({"results": []}), encoding="utf-8")
    sh(py + ["--apply", str(S / "empty.json")], env)
    out.append(("D5", "판정 안 된 사건은 인박스에 남음(유실 없음)", "race00000001" in inbox.read_text(encoding="utf-8"), ""))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", choices=["ai", "old"], default="ai")
    ap.add_argument("--code", default=str(REPO))
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--scale", type=int, default=1, help="케이스를 N 벌 복제 (한 번에 많이 판정)")
    ap.add_argument("--only", default="", help="쉼표로 케이스 id (예: C04,C20)")
    ap.add_argument("--prepare", action="store_true", help="샌드박스 + 줍기까지만 하고 멈춘다 (판정은 바깥 AI 가 --out 폴더에서)")
    ap.add_argument("--score", action="store_true", help="--out 샌드박스를 채점만 한다 (--prepare 다음)")
    a = ap.parse_args()
    global CASES
    if a.only:
        CASES = [c for c in CASES if c["id"] in a.only.split(",")]
    if a.scale > 1:                                    # 벌마다 대상이 다른 일 — 똑같이 복제하면 AI 가 중복으로 보고 하나만 남긴다(맞는 판단)
        CASES = [vary(c, k) for k in range(a.scale) for c in CASES]
    S = pathlib.Path(a.out or tempfile.mkdtemp(prefix="para-stress-"))
    if a.score:
        convo_case = json.loads((S / "cases.json").read_text(encoding="utf-8"))
        path_ids = json.loads((S / "path_ids.json").read_text(encoding="utf-8"))
        results = score(S, path_ids, convo_case)
        env = {"MILLIE_HOME": str(S), "MILLIE_VAULT": str(S / "vault")}
        det = [d for d in checks(S, env, "ai") if d[0] in ("D3",)]
        ok = sum(1 for r in results if r[2])
        print(f"# 바깥 AI 판정 채점 · {S}\n\n판정 {ok}/{len(results)}")
        for cid, name, good, why in results + det:
            print(f"  {'✅' if good else '❌'} {cid} {name}" + (f" — {why}" if why else ""))
        sys.exit(0 if ok == len(results) and all(d[2] for d in det) else 1)
    if S.exists() and any(S.iterdir()):
        shutil.rmtree(S)
    S.mkdir(parents=True, exist_ok=True)
    logs = []
    def log(step, rc, text):
        logs.append(f"### {step} rc={rc}\n{text.strip()}\n")
    env, vr = build(S, pathlib.Path(a.code))
    convo_case = write_sources(S, env, vr)
    err = None
    if a.prepare:
        rc, o, e = run_collect(S, ["--no-llm"])
        (S / "cases.json").write_text(json.dumps(convo_case, ensure_ascii=False), encoding="utf-8")
        (S / "path_ids.json").write_text(json.dumps(inbox_ids(S), ensure_ascii=False), encoding="utf-8")
        print(f"준비됨 {S} · 인박스 {len(inbox_ids(S))}건 — MILLIE_HOME={S} 로 para-sort 2~4단계를 돌린 뒤 --score --out {S}")
        return
    if a.no_ai:
        rc, o, e = run_collect(S, ["--no-llm"])
        log("collect", rc, o + e)
        path_ids = inbox_ids(S)
        results = [(c["id"], c["name"] + " — 수집", any(convo_case.get(p) == c["id"] for p in path_ids.values()), "") for c in CASES if not c["expect"].get("skip")]
    else:
        try:
            path_ids, err = (pipeline_ai if a.path == "ai" else pipeline_old)(S, log)
        except Exception as e:
            path_ids, err = inbox_ids(S), str(e)
        results = score(S, path_ids, convo_case)
    det = checks(S, env, a.path)
    if a.path == "ai" and a.no_ai:
        det += check_session_start(S, env)
    if a.no_ai:
        det = [d for d in det if d[0] != "D3"]           # 판정을 안 돌렸으니 파일까지 갔는지는 볼 수 없다
    if a.path == "ai" and not a.no_ai and not err:
        det += check_lock_and_race(S)
    (S / "stress.log").write_text("\n".join(logs), encoding="utf-8")
    ok = sum(1 for r in results if r[2])
    dok = sum(1 for r in det if r[2])
    print(f"# PARA 스트레스 테스트 · 경로 {a.path} · {S}")
    if err:
        print(f"!! 실행 오류: {err}")
    print(f"\n판정 {ok}/{len(results)}")
    for cid, name, good, why in results:
        print(f"  {'✅' if good else '❌'} {cid} {name}" + (f" — {why}" if why else ""))
    print(f"\n결정적 점검 {dok}/{len(det)}")
    for cid, name, good, why in det:
        print(f"  {'✅' if good else '❌'} {cid} {name}" + (f" — {why}" if why else ""))
    if not a.keep and not a.out:
        shutil.rmtree(S, ignore_errors=True)
    sys.exit(0 if ok == len(results) and dok == len(det) and not err else 1)


if __name__ == "__main__":
    main()
