#!/usr/bin/env python3
"""Install Millie for Codex without Claude, shell profiles, or desktop app bootstrap."""
import argparse
import datetime
import json
import os
import pathlib
import shlex
import shutil
import sys

from codex_permissions import configure, snippet

START = '<!-- millie-obsidian:start -->'
END = '<!-- millie-obsidian:end -->'


def merge_hook(config, command, remove=False):
    config = json.loads(json.dumps(config))
    hooks = config.setdefault('hooks', {})
    for event in ('SessionStart', 'UserPromptSubmit'):
        found = False
        groups = []
        for group in hooks.get(event, []):
            group = dict(group)
            handlers = []
            for handler in group.get('hooks', []):
                if handler.get('command') == command:
                    if remove or found:
                        continue
                    found = True
                handlers.append(handler)
            group['hooks'] = handlers
            groups.append(group)
        if not remove and not found:
            handler = {'type': 'command', 'command': command, 'timeout': 8,
                       'statusMessage': 'Millie: read-only project check', 'additionalContextLimit': 2000}
            if os.name == 'nt':
                # Codex's Windows hook override uses PowerShell invocation syntax.
                import shlex
                parts = shlex.split(command)
                quote = lambda value: "'" + value.replace("'", "''") + "'"
                handler['commandWindows'] = '& ' + ' '.join(quote(part) for part in parts)
            groups.append({'hooks': [handler]})
        hooks[event] = groups
    return config


def write(path, data, backup):
    data = data.encode() if isinstance(data, str) else data
    if path.exists() and path.read_bytes() == data:
        return
    if path.is_symlink():
        raise ValueError('Refusing symlink configuration destination: ' + str(path))
    if path.exists():
        saved = backup / path.name
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, saved)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def managed_block(old, body):
    if START not in old:
        return old.rstrip() + ('\n\n' if old.strip() else '') + START + '\n' + body.rstrip() + '\n' + END + '\n'
    if old.count(START) != 1 or old.count(END) != 1:
        raise ValueError('Malformed Millie managed block')
    before, tail = old.split(START, 1)
    _, after = tail.split(END, 1)
    return before + START + '\n' + body.rstrip() + '\n' + END + after


def install(home, framework, remove=False, permissions=False):
    home, framework = pathlib.Path(home).resolve(), pathlib.Path(framework).resolve()
    command = shlex.quote(sys.executable) + ' ' + shlex.quote(str(framework / 'plugin/hooks/codex_guard.py'))
    hooks_path = home / '.codex/hooks.json'
    old_hooks = json.loads(hooks_path.read_text()) if hooks_path.exists() else {}
    hooks = merge_hook(old_hooks, command, remove)
    backup = home / '.local/share/millie-install-backups' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    if remove:
        write(hooks_path, json.dumps(hooks, ensure_ascii=False, indent=2) + '\n', backup)
        print('Removed this checkout’s Codex hook; vault and unrelated hooks preserved')
        return
    cfg = json.loads((framework / 'config.json').read_text())
    vault = pathlib.Path(cfg['vault']).expanduser().resolve()
    if not vault.is_dir():
        raise ValueError('Configured vault does not exist: ' + str(vault))
    agents_path = home / '.codex/AGENTS.md'
    old_agents = agents_path.read_text() if agents_path.exists() else ''
    body = (framework / 'MILLIE.template.md').read_text().replace('{{VAULT}}', str(vault))
    agents = managed_block(old_agents, body)
    # Preflight configuration before writing any installation files.
    for p in (hooks_path, agents_path):
        if p.is_symlink():
            raise ValueError('Refusing symlink configuration destination: ' + str(p))
    if permissions:
        configure(home, [framework, vault])
    for source in sorted((framework / 'plugin/skills').iterdir()):
        if not (source / 'SKILL.md').is_file():
            continue
        target = home / '.agents/skills' / source.name
        if target.is_symlink() and target.resolve() == source.resolve():
            continue
        if target.exists() or target.is_symlink():
            print('Preserved existing skill; reconcile explicitly:', target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.symlink_to(source, target_is_directory=True)
        except OSError:
            # Windows without symlink privileges can still discover a complete skill copy.
            shutil.copytree(source, target)
    write(hooks_path, json.dumps(hooks, ensure_ascii=False, indent=2) + '\n', backup)
    write(agents_path, agents, backup)
    write(home / '.local/share/millie/codex-permissions.toml', snippet([framework, vault]), backup)
    print('Codex installed. Restart and review/trust the new hooks in /hooks.')
    print('Data writes require access to:', framework, vault)
    print('Optional permission configuration: --configure-codex-permissions (Python 3.11+).')
    print('Managed/session policies can override user config; no full-access or trust bypass is enabled.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=pathlib.Path, default=pathlib.Path.home())
    parser.add_argument('--framework-home', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument('--remove', action='store_true')
    parser.add_argument('--configure-codex-permissions', action='store_true')
    args = parser.parse_args()
    install(args.home, args.framework_home, args.remove, args.configure_codex_permissions)
