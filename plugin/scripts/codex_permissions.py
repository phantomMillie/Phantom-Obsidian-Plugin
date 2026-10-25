"""Opt-in Codex data-directory access; never broad access or approval-policy changes."""
import datetime
import json
import pathlib
import re
import shutil
import os
import tempfile


def snippet(roots):
    return '[sandbox_workspace_write]\nwritable_roots = ' + json.dumps([str(p) for p in roots], ensure_ascii=False) + '\n'


def configure(home, roots):
    """Preserve unrelated TOML, reject unsupported policies before writing anything."""
    try:
        import tomllib
    except ImportError:
        raise ValueError('Permission configuration requires Python 3.11+; use the generated permissions snippet instead')
    path = pathlib.Path(home) / '.codex/config.toml'
    if path.is_symlink():
        raise ValueError('Refusing symlink config.toml; update the managed source explicitly')
    old = path.read_text(encoding='utf-8') if path.exists() else ''
    before = tomllib.loads(old)
    if 'default_permissions' in before or 'permissions' in before:
        raise ValueError('Named permission profiles are active; add these exact data paths to the selected profile instead')
    if before.get('sandbox_mode') == 'read-only':
        raise ValueError('Read-only mode is configured; choose a write-capable mode before granting data paths')
    roots = list(dict.fromkeys([str(p) for p in before.get('sandbox_workspace_write', {}).get('writable_roots', [])] + [str(p) for p in roots]))
    value = json.dumps(roots, ensure_ascii=False)
    table = re.search(r'^\s*\[sandbox_workspace_write\]\s*(?:#.*)?$', old, re.M)
    if table:
        start = table.end()
        next_table = re.search(r'^\s*\[\[?[\w"\']', old[start:], re.M)
        end = start + next_table.start() if next_table else len(old)
        body = old[start:end]
        key = re.search(r'^\s*writable_roots\s*=\s*', body, re.M)
        if key:
            value_start = key.end()
            lines = body[value_start:].splitlines(keepends=True)
            consumed = ''
            for line in lines:
                consumed += line
                try:
                    tomllib.loads('v=' + consumed)
                    break
                except tomllib.TOMLDecodeError:
                    continue
            else:
                raise ValueError('Cannot safely locate writable_roots value')
            body = body[:key.start()] + '\nwritable_roots = ' + value + '\n' + body[value_start+len(consumed):]
        else:
            body = '\nwritable_roots = ' + value + '\n' + body.lstrip('\n')
        updated = old[:start] + body + old[end:]
    else:
        updated = old.rstrip() + '\n\n' + snippet(roots)
    after = tomllib.loads(updated)
    expected = dict(before)
    expected['sandbox_workspace_write'] = dict(before.get('sandbox_workspace_write', {}), writable_roots=roots)
    if after != expected:
        raise ValueError('Permission merge would change unrelated configuration')
    if updated == old:
        return False
    if path.exists():
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        shutil.copy2(path, path.with_name(path.name + '.' + stamp + '.bak'))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.codex-permissions-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(updated)
        os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True
