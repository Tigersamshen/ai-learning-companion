#!/usr/bin/env python3
"""增量注册个人插件。默认只生成草稿；--apply 才修改目录并调用官方 CLI。"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from runtime_config import resolve_data_root

PLUGIN = Path(__file__).resolve().parents[1]
DATA = resolve_data_root()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.plugin-install-')
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    codex = shutil.which('codex')
    if not codex:
        raise ValueError('未找到官方 codex CLI')
    listing = subprocess.run([codex, 'plugin', 'marketplace', 'list', '--json'], check=True, capture_output=True, text=True)
    marketplaces = json.loads(listing.stdout)
    entries = marketplaces.get('marketplaces', marketplaces) if isinstance(marketplaces, dict) else marketplaces
    personal = next((p for p in entries if p.get('name') == 'personal'), None)
    if not personal:
        raise ValueError('没有已有 personal 插件目录；本工具不会创建替代目录')
    root = Path(personal['root']).resolve()
    manifest = root / '.agents' / 'plugins' / 'marketplace.json'
    original = manifest.read_bytes()
    value = json.loads(original)
    if value.get('name') != 'personal':
        raise ValueError('personal 目录名称不匹配')
    relative = './' + str(PLUGIN.relative_to(root))
    entry = {'name': 'ai-learning-companion', 'source': {'source': 'local', 'path': relative},
             'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'}, 'category': 'Productivity'}
    existing = next((p for p in value['plugins'] if p.get('name') == entry['name']), None)
    if existing and existing != entry:
        raise ValueError('同名插件已登记到其他配置；保留现有条目并停止')
    if existing is None:
        value['plugins'].append(entry)
    folder = DATA / 'verification' / 'installation'
    save(folder / 'marketplace-proposed.json', value)
    result = {'ok': True, 'applied': args.apply, 'marketplace': str(manifest), 'source': str(PLUGIN),
              'proposed': str(folder / 'marketplace-proposed.json')}
    if args.apply:
        if manifest.read_bytes() != original:
            raise ValueError('marketplace.json 在准备期间变化；停止写入')
        if not existing:
            backup = folder / ('marketplace-before-' + hashlib.sha256(original).hexdigest()[:12] + '.json')
            if not backup.exists():
                backup.write_bytes(original)
            save(manifest, value)
            result['backup'] = str(backup)
        process = subprocess.run([codex, 'plugin', 'add', 'ai-learning-companion@personal', '--json'], capture_output=True, text=True)
        result['install_exit_code'] = process.returncode
        try:
            result['installation'] = json.loads(process.stdout)
        except ValueError:
            result['installation'] = process.stdout.strip()
        result['ok'] = process.returncode == 0
        if process.returncode:
            result['error'] = process.stderr.strip()
        result['at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save(folder / 'install-result.json', result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        raise SystemExit(1)
