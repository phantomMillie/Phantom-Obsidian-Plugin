#!/usr/bin/env python3
# 설정 읽기 — ~/.millie-obsidian/config.json (gitignore, 이 PC 에만 있다).
# vault 별 경로 · 이름 · 로컬 비밀 파일 위치는 전부 설정에 둔다. 프레임워크 코드 · 스킬에는 키 이름만 쓴다.
# 구조는 config.example.json 참고. 없는 키는 아래 기본값(일반 PARA 이름)을 쓴다.
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent           # ~/.millie-obsidian

DEFAULTS = {
    "paths": {                                                   # vault 기준 상대 경로
        "projects": "Projects",
        "areas": "Areas",
        "resources": "Resources",
        "archives": "Archives",
        "store": "Store",
        "para_inbox": "📥 PARA 인박스.md",
        "para_history": "📤 PARA 이동 히스토리.md",
    },
    "classify": {
        "fallback_project": "Unsorted",                          # 판정 불가 사건이 가는 프로젝트
        "resource_skip": [],                                     # 자료 주제에서 뺄 Resources 하위 폴더
    },
    "local": {                                                   # vault 밖, 이 PC 의 파일
        "anthropic_key": "~/.config/phantom-obsidian/anthropic-key",
        "llm_cmd": "~/.config/phantom-obsidian/llm-cmd",
        "slack_webhook": "~/.config/phantom-obsidian/slack-webhook",
    },
}

_cache = None


def load():
    global _cache
    if _cache is None:
        try:
            user = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            sys.exit(f"설정 읽기 실패 ({ROOT / 'config.json'}): {e} — config.example.json 을 복사해 채운다")
        merged = {k: dict(v) for k, v in DEFAULTS.items()}
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            else:
                merged[k] = v
        _cache = merged
    return _cache


def vault():
    v = pathlib.Path(load().get("vault", "")).expanduser()
    if not str(v) or not v.is_dir():
        sys.exit(f"vault 폴더 없음: {v} — config.json 의 vault 확인")
    return v


def vpath(key):
    """vault 안 경로. 설정에 없으면 None."""
    rel = load()["paths"].get(key)
    return vault() / rel if rel else None


def local(key):
    p = load()["local"].get(key)
    return pathlib.Path(p).expanduser() if p else None


def classify_opt(key):
    return load()["classify"].get(key)
