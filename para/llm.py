#!/usr/bin/env python3
# PARA 공용 LLM 호출 — 수집기(collect.py) · 분류기(classify.py)가 같이 쓴다.
#
# 외부 LLM 조건 (Q15, 사용자 결정 2026-10-08): 업무 대화는 학습에 쓰지 않는 계약으로만 보낸다.
#   허용: API 키(상업 약관) 또는 `claude` CLI 가 Team · Enterprise 계정.
#   차단: 개인 요금제(Free · Pro · Max), 계정 확인 실패, LLM 명령이 claude 가 아님(계약 확인 불가).
#   → 부르는 쪽은 llm_allowed() 가 False 면 LLM 없는 경로로 간다.
#
# 경로: API 키가 있으면 Messages API, 없으면 `claude -p` (개발일지 분배와 같은 방식).
# launchd 에서는 CLI 인증(키체인)이 막히므로 배치로 돌리려면 API 키(config.json `local.anthropic_key`)가 필요하다.
import json, os, pathlib, re, shlex, shutil, subprocess, sys, urllib.error, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config  # noqa: E402

HOME = pathlib.Path.home()
API_URL = "https://api.anthropic.com/v1/messages"
API_MODEL = "claude-opus-5-5"
API_EFFORT = "low"                          # 요약 · 분할 · 분류는 단순 작업
API_VERSION = "2023-06-01"
API_BETA = "server-side-fallback-2026-07-01"  # 거절 시 서버가 대체 모델로 재시도
COMMERCIAL_PLANS = {"team", "enterprise"}


def _read(p):
    try:
        return p.read_text().strip() if p and p.exists() else ""
    except OSError:
        return ""


def _resolve_bin(name):
    if "/" in name:
        return name
    hit = shutil.which(name)
    if hit:
        return hit
    for d in (HOME / ".local/bin", pathlib.Path("/opt/homebrew/bin"), pathlib.Path("/usr/local/bin")):
        if (d / name).exists():
            return str(d / name)
    return name


def api_key():
    return os.environ.get("ANTHROPIC_API_KEY", "").strip() or _read(config.local("anthropic_key"))


def llm_allowed():
    """(허용 여부, 이유). 업무 대화를 학습에 쓰지 않는 계약인지 확인한다."""
    if api_key():
        return True, "API 키 (상업 약관)"
    raw = _read(config.local("llm_cmd"))
    if raw and os.path.basename(shlex.split(raw)[0]) != "claude":
        return False, f"LLM 명령이 claude 가 아님({shlex.split(raw)[0]}) — 계약 확인 불가"
    try:
        r = subprocess.run([_resolve_bin("claude"), "auth", "status"], capture_output=True, text=True, timeout=30)
        st = json.loads(r.stdout)
    except Exception as e:
        return False, f"claude 계정 확인 실패: {e}"
    plan = str(st.get("subscriptionType") or "").lower()
    if plan in COMMERCIAL_PLANS:
        return True, f"claude {plan} 계정 ({st.get('orgName', '')})"
    return False, f"claude 계정이 개인 요금제({plan or '알 수 없음'}) — 학습 설정을 확인할 수 없어 LLM 안 씀"


def parse_json(text):
    text = re.sub(r"^```[a-z]*\n|\n```$", "", (text or "").strip())
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError(f"LLM 응답 파싱 실패: {text[:200]}")
    return json.loads(m.group(0))


def _api(prompt, schema, key):
    body = json.dumps({
        "model": API_MODEL,
        "max_tokens": 16000,
        "fallbacks": "default",
        "output_config": {"effort": API_EFFORT, "format": {"type": "json_schema", "schema": schema}},
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, headers={
        "content-type": "application/json",
        "x-api-key": key,
        "anthropic-version": API_VERSION,
        "anthropic-beta": API_BETA,
    })
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"API {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}")
    except Exception as e:
        raise RuntimeError(f"API 호출 실패: {e}")
    if data.get("stop_reason") == "refusal":
        raise RuntimeError("API 거부(refusal)")
    if data.get("stop_reason") == "max_tokens":
        raise RuntimeError("API 응답이 max_tokens 에서 잘림")
    return parse_json("".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"))


def _cli(prompt):
    raw = _read(config.local("llm_cmd"))
    cmd = shlex.split(raw) if raw else ["claude", "-p"]
    cmd[0] = _resolve_bin(cmd[0])
    env = dict(os.environ)
    env["PATH"] = env.get("PATH", "") + ":" + ":".join([str(HOME / ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"])
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=600, env=env)
    except FileNotFoundError:
        raise RuntimeError(f"LLM CLI 없음: {cmd[0]}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("LLM 응답 시간 초과(600s)")
    if r.returncode != 0:
        raise RuntimeError(f"LLM 실패: {(r.stderr or r.stdout or '').strip()[:200]}")
    return parse_json(r.stdout)


def call(prompt, schema):
    """(JSON 객체, 'api' | 'cli'). 실패하면 RuntimeError. 부르기 전에 llm_allowed() 를 확인할 것."""
    key = api_key()
    return (_api(prompt, schema, key), "api") if key else (_cli(prompt), "cli")
