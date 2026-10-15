"""프레임워크 홈(config.json · vault 가 있는 곳)을 찾는다.

Claude Code 는 플러그인을 ~/.claude/plugins/cache/ 에 복사해서 돌린다. 그래서 스크립트 위치를
기준으로 올라가면 캐시 폴더가 나오고, 거기엔 config.json 이 없다(gitignore 대상이라 레포 밖 파일).
홈을 고정 경로로 찾아야 캐시에서 돌아도 같은 설정을 읽는다.

찾는 순서
  1. PHANTOM_HOME 환경변수 — 주어지면 조건 없이 이긴다(처음 설치 때는 config.json 이 아직 없다)
  2. 스크립트에서 세 단계 위 — 레포에서 직접 돌릴 때 (<repo>/plugin/scripts/x.py → <repo>)
  3. ~/.phantom-obsidian — install.sh 가 쓰는 기본 자리
2·3 중에서는 config.json 이 있는 첫 후보를 쓰고, 하나도 없으면 3번을 돌려준다.
"""
import os
import pathlib

__all__ = ["phantom_home", "load_config", "vault_path"]

DEFAULT = pathlib.Path.home() / ".phantom-obsidian"


def _candidates(start):
    if start is not None:
        # <repo>/plugin/scripts/x.py · <repo>/plugin/hooks/x.py → <repo>
        yield pathlib.Path(start).resolve().parent.parent.parent
    yield DEFAULT


def phantom_home(start=None):
    # PHANTOM_HOME 은 조건 없이 이긴다 — 처음 설치할 때는 config.json 이 아직 없다.
    env = os.environ.get("PHANTOM_HOME")
    if env:
        return pathlib.Path(env).expanduser()
    for c in _candidates(start):
        if (c / "config.json").is_file():
            return c
    return DEFAULT


def load_config(start=None):
    """config.json 을 읽는다. 없으면 FileNotFoundError."""
    import json

    return json.loads((phantom_home(start) / "config.json").read_text(encoding="utf-8"))


def vault_path(start=None):
    """config 의 vault 경로. 없으면 None."""
    try:
        v = load_config(start).get("vault")
    except (OSError, ValueError):
        return None
    return pathlib.Path(v).expanduser() if v else None
