#!/usr/bin/env python3
"""vault 를 Obsidian 에서 바로 열 수 있게 만든다 — 커뮤니티 플러그인 설치 · 설정 · vault 등록.

  python3 obsidian_setup.py <vault> [--skip-download] [--skip-register]
  python3 obsidian_setup.py <vault> --unregister      vault 목록에서만 뺀다 (파일은 그대로)

하는 일
  1. Templater · Dataview 최신 릴리스를 <vault>/.obsidian/plugins/<id>/ 에 받는다
  2. community-plugins.json 에 둘을 켠다 (이미 켜진 다른 플러그인은 그대로)
  3. Templater 템플릿 폴더 = Templetes, Dataview JS 쿼리 = 켬
  4. Obsidian 의 vault 목록(obsidian.json)에 이 vault 를 등록한다

여러 번 돌려도 같은 결과. 네트워크가 없으면 내려받기만 건너뛰고 설정은 끝낸다.
사용자가 손으로 바꾼 설정 값은 덮지 않는다 — 없는 키만 채운다.
"""
import json
import pathlib
import sys
import urllib.error
import urllib.request

# (플러그인 id, GitHub 레포, 필수 파일 여부)
PLUGINS = [
    ("templater-obsidian", "SilentVoid13/Templater"),
    ("dataview", "blacksmithgu/obsidian-dataview"),
]
ASSETS = ["main.js", "manifest.json", "styles.css"]

# 플러그인별 기본 설정 — 이미 값이 있으면 건드리지 않는다.
PLUGIN_DEFAULTS = {
    "templater-obsidian": {"templates_folder": "Templetes"},
    "dataview": {"enableDataviewJs": True, "enableInlineDataviewJs": True},
}


def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "phantom-obsidian"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read()


def download_plugin(vault, plugin_id, repo):
    """최신 릴리스 파일을 받는다. 이미 main.js 가 있으면 건너뛴다."""
    dest = vault / ".obsidian" / "plugins" / plugin_id
    if (dest / "main.js").exists():
        return "이미 있음 %s" % plugin_id
    try:
        release = json.loads(fetch("https://api.github.com/repos/%s/releases/latest" % repo))
    except (urllib.error.URLError, ValueError, OSError) as e:
        return "건너뜀 %s (릴리스 조회 실패: %s)" % (plugin_id, e)

    urls = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    dest.mkdir(parents=True, exist_ok=True)
    got = []
    for name in ASSETS:
        if name not in urls:
            continue  # styles.css 가 없는 플러그인도 있다
        try:
            (dest / name).write_bytes(fetch(urls[name]))
            got.append(name)
        except (urllib.error.URLError, OSError) as e:
            return "실패 %s/%s (%s)" % (plugin_id, name, e)
    if "main.js" not in got:
        return "실패 %s (main.js 없음)" % plugin_id
    return "설치 %s %s" % (plugin_id, release.get("tag_name", ""))


def enable_plugins(vault, plugin_ids):
    path = vault / ".obsidian" / "community-plugins.json"
    enabled = read_json(path, [])
    if not isinstance(enabled, list):
        enabled = []
    added = [p for p in plugin_ids if p not in enabled]
    if added:
        write_json(path, enabled + added)
    return "켬 %s" % ", ".join(added) if added else "이미 켜짐"


def apply_defaults(vault, plugin_id):
    """플러그인 data.json 에 없는 키만 채운다."""
    path = vault / ".obsidian" / "plugins" / plugin_id / "data.json"
    data = read_json(path, {})
    if not isinstance(data, dict):
        return None
    missing = {k: v for k, v in PLUGIN_DEFAULTS.get(plugin_id, {}).items() if k not in data}
    if not missing:
        return None
    data.update(missing)
    write_json(path, data)
    return "설정 %s %s" % (plugin_id, ", ".join(missing))


def obsidian_config_dir():
    """OS 별 Obsidian 설정 폴더. 없으면 None."""
    home = pathlib.Path.home()
    for p in (
        home / "Library/Application Support/obsidian",      # macOS
        home / ".config/obsidian",                           # Linux
        home / "AppData/Roaming/obsidian",                   # Windows
    ):
        if p.is_dir():
            return p
    return None


def register_vault(vault):
    """Obsidian 의 vault 목록에 추가한다. Obsidian 이 켜져 있으면 끄고 다시 켜야 보인다."""
    cfg_dir = obsidian_config_dir()
    if cfg_dir is None:
        return "건너뜀 vault 등록 (Obsidian 설정 폴더 없음 — 앱에서 'Open folder as vault' 로 연다)"
    path = cfg_dir / "obsidian.json"
    cfg = read_json(path, {})
    vaults = cfg.setdefault("vaults", {})
    target = str(vault)
    if any(v.get("path") == target for v in vaults.values()):
        return "이미 등록됨 vault"
    # Obsidian 은 경로 해시를 키로 쓴다. 충돌만 피하면 되므로 경로로 안정적인 키를 만든다.
    import hashlib

    key = hashlib.md5(target.encode("utf-8")).hexdigest()[:16]
    # ts 는 Obsidian 이 '최근 연 vault' 정렬에 쓴다. 0 이면 목록 맨 아래.
    vaults[key] = {"path": target, "ts": 0}
    write_json(path, cfg)
    return "등록 vault (Obsidian 을 껐다 켜면 목록에 보인다)"


def unregister_vault(vault):
    """Obsidian 의 vault 목록에서 뺀다. vault 폴더 자체는 건드리지 않는다."""
    cfg_dir = obsidian_config_dir()
    if cfg_dir is None:
        return "건너뜀 vault 등록 해제 (Obsidian 설정 폴더 없음)"
    path = cfg_dir / "obsidian.json"
    cfg = read_json(path, {})
    vaults = cfg.get("vaults")
    if not isinstance(vaults, dict):
        return "건너뜀 vault 등록 해제 (목록 없음)"
    target = str(vault)
    gone = [k for k, v in vaults.items() if v.get("path") == target]
    if not gone:
        return "등록 안 돼 있음"
    for k in gone:
        del vaults[k]
    write_json(path, cfg)
    return "등록 해제 vault"


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(__doc__.strip(), file=sys.stderr)
        return 1
    vault = pathlib.Path(argv[0]).expanduser().resolve()

    if "--unregister" in argv:
        # vault 폴더가 이미 지워진 뒤에 불릴 수 있으므로 존재를 따지지 않는다.
        print(unregister_vault(vault))
        return 0

    if not vault.is_dir():
        print("vault 폴더가 없다: %s" % vault, file=sys.stderr)
        return 1

    lines = []
    if "--skip-download" not in argv:
        for plugin_id, repo in PLUGINS:
            lines.append(download_plugin(vault, plugin_id, repo))

    # main.js 가 실제로 있는 것만 켠다 — 없는 걸 켜면 Obsidian 이 시작할 때 오류를 낸다.
    installed = [
        p for p, _ in PLUGINS if (vault / ".obsidian/plugins" / p / "main.js").exists()
    ]
    if installed:
        lines.append(enable_plugins(vault, installed))
    for plugin_id in installed:
        note = apply_defaults(vault, plugin_id)
        if note:
            lines.append(note)

    if "--skip-register" not in argv:
        lines.append(register_vault(vault))

    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
