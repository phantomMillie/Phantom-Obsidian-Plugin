#!/usr/bin/env python3
"""Optional adapters for already-installed third-party skills; no Cloud or provider calls."""
import argparse
import hashlib
import json
import pathlib
import re
import shutil


def digest(data):
    return hashlib.sha256(data).hexdigest()


def adapt_caveman(name, text, stats_script):
    if name == 'caveman-explore':
        text = re.sub(r'^(tools|model):.*\n', '', text, flags=re.M)
        text += '\n## Codex execution\n\nUse the current host’s read-only search and file-reading tools. Claude tool names and the haiku model are not required. Use delegation only when available and authorized; otherwise explore directly and do not claim the reads stayed outside main context.\n'
    elif name == 'cavecrew':
        text += '\n## Codex execution\n\nThe preset names above are Claude-specific, not installed Codex agent types. When delegation is available and authorized, give the host’s agent tool the same role and output contract. Otherwise locate, edit, and review directly. Do not claim independent agents ran or measured token savings.\n'
    elif name == 'caveman-stats':
        front = text.split('---', 2)[1]
        text = '---' + front + '---\n\n# Codex session statistics\n\nRun `python3 ' + json.dumps(str(stats_script), ensure_ascii=False) + '`. It verifies the exact CODEX_THREAD_ID when available; otherwise supply an explicitly identified file with `--session`. Never substitute the newest session or a Claude transcript. Report actual token counters only; savings need a paired baseline. No Claude blocking hook is required.\n'
    if name in {'caveman-learn', 'caveman-discover', 'caveman-evidence-review', 'caveman-manage', 'caveman-optimize', 'caveman-setup'}:
        parts = text.split('---', 2)
        guard = '\n\n## Runtime capability check\n\nUse only Caveman MCP tools exposed by this host or an installed caveman CLI. A copied skill does not install the Cloud service, CLI, account, or project selection. If a dependency is missing, identify it and stop that step. Never fabricate telemetry or silently configure an account or gateway. Existing production-control requirements still apply.\n'
        text = '---' + parts[1] + '---' + guard + parts[2]
    if name == 'caveman':
        text += '\n## Host instruction precedence\n\nCompress wording within the host’s communication requirements. Keep progress updates required by higher-priority instructions.\n'
    return text


def engineering_patches(skill_root):
    out = {}
    path = skill_root / 'improve-codebase-architecture/SKILL.md'
    if path.is_file():
        old = path.read_text()
        anchor = 'Then use the Agent tool with `subagent_type=Explore` to walk the codebase.'
        if anchor in old:
            out[path] = old.replace(anchor, 'Walk the codebase with the host’s available search and file-reading tools. If authorized delegation is available, use the host’s agent tool; otherwise explore directly. Do not require Claude-specific tool names.').encode()
    path = skill_root / 'improve-codebase-architecture/INTERFACE-DESIGN.md'
    if path.is_file():
        old = path.read_text()
        anchor = 'Spawn 3+ sub-agents in parallel using the Agent tool.'
        if anchor in old:
            out[path] = old.replace(anchor, 'Use authorized host-native delegation for three alternatives when available. Otherwise produce the three alternatives sequentially and disclose that they are not independent reviews.').encode()
    path = skill_root / 'setup-matt-pocock-skills/SKILL.md'
    if path.is_file():
        old = path.read_text()
        start = old.find('**Pick the file to edit:**')
        end = old.find('If an `## Agent skills` block', start)
        if start >= 0 and end >= 0:
            replacement = '''**Pick the instruction entrypoint the host discovers:**

- Codex: `AGENTS.md`; Claude Code: `CLAUDE.md`. Preserve explicit repository policy.
- Read existing entrypoints first. If both exist, update the current host's file and keep shared docs as the source of truth.
- If only the other host's file exists, include a minimal entrypoint/reference for the current host in the draft above and obtain the same confirmation before creating it. Do not assume automatic cross-host loading.
- If neither exists, propose the current host's entrypoint in that draft.

'''
            out[path] = (old[:start] + replacement + old[end:]).encode()
        meta = path.parent / 'agents/openai.yaml'
        if 'disable-model-invocation: true' in old and not meta.exists():
            out[meta] = b'policy:\n  allow_implicit_invocation: false\n'
    return out


def discover_caveman(home):
    registry = home / '.claude/plugins/installed_plugins.json'
    if not registry.is_file():
        return None
    data = json.loads(registry.read_text())
    entries = data.get('plugins', {}).get('caveman@caveman', [])
    if not entries:
        return None
    return pathlib.Path(entries[0]['installPath'])


def install(home, framework, caveman_source=None):
    home, framework = pathlib.Path(home).resolve(), pathlib.Path(framework).resolve()
    skills = home / '.agents/skills'
    ledger_path = home / '.local/share/millie/skill-compat.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    files = engineering_patches(skills)
    source = pathlib.Path(caveman_source).resolve() if caveman_source else discover_caveman(home)
    imported = []
    if source:
        for folder in sorted((source / 'skills').iterdir()):
            if not (folder / 'SKILL.md').is_file():
                continue
            target_root = skills / folder.name
            existing = target_root / 'SKILL.md'
            if existing.exists() and str(existing) not in ledger:
                print('Preserved existing unmanaged skill:', existing)
                continue
            for path in sorted(folder.rglob('*')):
                if not path.is_file() or '__pycache__' in path.parts or path.name.startswith('.'):
                    continue
                if not path.resolve().is_relative_to(folder.resolve()):
                    raise ValueError('Resource escapes its skill folder: ' + str(path))
                target = target_root / path.relative_to(folder)
                data = path.read_bytes()
                if path.name == 'SKILL.md':
                    data = adapt_caveman(folder.name, data.decode(), framework / 'plugin/scripts/codex_stats.py').encode()
                files[target] = data
            imported.append(folder.name)
    else:
        print('Caveman source not installed. Supply --caveman-source with a local upstream checkout to import its skills.')
    # Do not replace independent user edits on repeat installs.
    for path, data in files.items():
        if path.exists() and path.read_bytes() != data and str(path) in ledger:
            if digest(path.read_bytes()) != ledger[str(path)]['sha256']:
                raise ValueError('Preserved modified managed skill; reconcile explicitly: ' + str(path))
        if path.is_symlink():
            raise ValueError('Refusing a symlink file destination: ' + str(path))
    backup_root = home / '.local/share/millie/skill-compat-backups'
    for path, data in files.items():
        if path.exists() and path.read_bytes() == data:
            continue
        if path.exists():
            saved = backup_root / path.relative_to(skills)
            saved.parent.mkdir(parents=True, exist_ok=True)
            if not saved.exists():
                shutil.copy2(path, saved)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        ledger[str(path)] = {'sha256': digest(data)}
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
    gemini_skills = home / '.gemini/config/skills'
    if gemini_skills.exists() or (home / '.gemini').exists():
        gemini_skills.mkdir(parents=True, exist_ok=True)
        for folder in skills.iterdir():
            if folder.is_dir() and (folder / 'SKILL.md').is_file():
                link = gemini_skills / folder.name
                if not link.exists() and not link.is_symlink():
                    try:
                        link.symlink_to(folder, target_is_directory=True)
                    except OSError:
                        pass
        gemini_skills_json = home / '.gemini/config/skills.json'
        old_data = json.loads(gemini_skills_json.read_text()) if gemini_skills_json.exists() else {'entries': []}
        entries = old_data.setdefault('entries', [])
        paths = [e.get('path') for e in entries if isinstance(e, dict)]
        if str(skills) not in paths:
            entries.append({'path': str(skills)})
            gemini_skills_json.parent.mkdir(parents=True, exist_ok=True)
            gemini_skills_json.write_text(json.dumps(old_data, indent=2, ensure_ascii=False) + '\n')
    print('Imported Caveman skills:', len(imported))
    print('Cloud workflows still require a real CLI/MCP connection and account; no service or credentials were configured.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=pathlib.Path, default=pathlib.Path.home())
    parser.add_argument('--framework-home', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument('--caveman-source', type=pathlib.Path)
    args = parser.parse_args()
    install(args.home, args.framework_home, args.caveman_source)
