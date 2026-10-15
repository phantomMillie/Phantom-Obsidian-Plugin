#!/usr/bin/env python3
"""첫 실행 준비 — 플러그인만 받아도 vault · Obsidian 설정 · 바탕화면 TODO 앱이 저절로 깔리게 한다.

  bootstrap.py           빠진 것만 채운다 (여러 번 돌려도 같은 결과)
  bootstrap.py --fast    vault 만 (몇 ms) — 세션 시작 훅이 먼저 부른다

SessionStart 훅(hooks/project_guard.py)이 부른다. 사용자가 따로 돌릴 일은 없다.
  1. config.json · vault 가 없으면 ~/.phantom-obsidian/vault 를 만든다
  2. Templater · Dataview 설치 + Obsidian vault 등록 (네트워크 필요, 실패하면 하루 뒤 다시)
  3. macOS 면 TODO 앱을 빌드하고 로그인 때 자동 실행 (swiftc 필요, 없으면 하루 뒤 다시)
결과는 <홈>/state/bootstrap.json, 로그는 <홈>/state/bootstrap.log.
PHANTOM_NO_TODO_PILE=1 이면 3번을 건너뛴다.
"""
import datetime
import fcntl
import hashlib
import json
import os
import pathlib
import plistlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
PLUGIN = HERE.parent
sys.path.insert(0, str(HERE))
from phantom_home import phantom_home           # noqa: E402

HOME = phantom_home(__file__)
STATE_DIR = HOME / "state"
STATE = STATE_DIR / "bootstrap.json"
LOG = STATE_DIR / "bootstrap.log"
RETRY = datetime.timedelta(days=1)
LABEL = "com.phantom.todo-pile"


def now():
    return datetime.datetime.now()


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(st):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def log(msg):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write("%s %s\n" % (now().isoformat(timespec="seconds"), msg))


def due(st, step, key=""):
    """이 단계를 지금 돌려야 하나. 성공했고 key 가 같으면 안 한다. 실패는 하루 뒤 다시."""
    s = st.get(step) or {}
    if s.get("ok") and s.get("key", "") == key:
        return False
    if not s.get("ok") and s.get("key", "") == key and s.get("at"):
        try:
            return now() - datetime.datetime.fromisoformat(s["at"]) > RETRY
        except ValueError:
            return True
    return True


def done(st, step, ok, key=""):
    st[step] = {"ok": ok, "key": key, "at": now().isoformat(timespec="seconds")}
    save_state(st)


def vault_dir():
    try:
        return pathlib.Path(json.loads((HOME / "config.json").read_text(encoding="utf-8"))["vault"]).expanduser()
    except Exception:
        return None


def ensure_vault():
    """config.json · vault 가 없으면 새로 만든다. 이미 있으면 아무것도 안 한다."""
    if vault_dir() and vault_dir().is_dir():
        return True
    env = dict(os.environ, PHANTOM_HOME=str(HOME))
    r = subprocess.run([sys.executable, str(HERE / "vault_init.py"), str(HOME / "vault"), "--set-default"],
                       capture_output=True, text=True, env=env, timeout=60)
    log("vault_init rc=%d %s" % (r.returncode, (r.stdout + r.stderr).strip()[-300:]))
    return r.returncode == 0


def ensure_obsidian(st):
    v = vault_dir()
    if not v or not due(st, "obsidian"):
        return
    r = subprocess.run([sys.executable, str(HERE / "obsidian_setup.py"), str(v)],
                       capture_output=True, text=True, timeout=300)
    log("obsidian_setup rc=%d %s" % (r.returncode, (r.stdout + r.stderr).strip()[-300:]))
    done(st, "obsidian", r.returncode == 0)


def ensure_todo_pile(st):
    src = PLUGIN / "tools" / "todo-pile" / "Pile.swift"
    if sys.platform != "darwin" or os.environ.get("PHANTOM_NO_TODO_PILE") or not src.is_file():
        return
    key = hashlib.sha256(src.read_bytes()).hexdigest()[:16]
    binary = HOME / "bin" / "todo-pile"
    if not due(st, "todo_pile", key) and binary.exists():
        return
    if not shutil.which("swiftc"):
        log("todo-pile 건너뜀: swiftc 없음 (xcode-select --install)")
        done(st, "todo_pile", False, key)
        return
    binary.parent.mkdir(parents=True, exist_ok=True)
    tmp = binary.with_name("todo-pile.new")
    r = subprocess.run(["swiftc", "-O", str(src), "-o", str(tmp)], capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        log("todo-pile 빌드 실패: %s" % r.stderr.strip()[-300:])
        done(st, "todo_pile", False, key)
        return
    os.replace(tmp, binary)
    plist = pathlib.Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_bytes(plistlib.dumps({
        "Label": LABEL, "ProgramArguments": [str(binary)], "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False}}))
    uid = str(os.getuid())
    subprocess.run(["launchctl", "bootout", "gui/%s/%s" % (uid, LABEL)], capture_output=True)
    r = subprocess.run(["launchctl", "bootstrap", "gui/" + uid, str(plist)], capture_output=True, text=True)
    log("todo-pile 설치 rc=%d %s" % (r.returncode, r.stderr.strip()[-200:]))
    done(st, "todo_pile", r.returncode == 0, key)


def main(argv):
    if not ensure_vault():
        sys.exit(1)
    if "--fast" in argv:
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with (STATE_DIR / "bootstrap.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return                                   # 다른 쪽이 이미 돌고 있다
        st = load_state()
        for step in (ensure_obsidian, ensure_todo_pile):
            try:
                step(st)
            except Exception as e:                   # 한 단계가 죽어도 다음 단계는 간다
                log("%s 오류: %s" % (step.__name__, e))


if __name__ == "__main__":
    main(sys.argv[1:])
