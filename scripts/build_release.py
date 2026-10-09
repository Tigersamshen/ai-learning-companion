#!/usr/bin/env python3
"""Build a clean, reproducible ZIP from the explicit distributable allowlist."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ALLOW = ('README.md', 'CHANGELOG.md', '.gitignore', '.agents', 'plugins', 'setup.py', 'Install.command', 'tests', 'scripts', 'AGENTS.md', 'LICENSE')
EXCLUDE = {'__pycache__', '.git', '.DS_Store', '.obsidian'}


def files():
    for name in ALLOW:
        item = ROOT / name
        if not item.exists():
            raise ValueError('Missing distribution component: ' + name)
        for path in sorted(item.rglob('*')) if item.is_dir() else [item]:
            if path.is_symlink():
                raise ValueError('Symlinks are not allowed in the release: ' + str(path.relative_to(ROOT)))
            if path.is_file() and not (set(path.parts) & EXCLUDE) and path.suffix not in ('.pyc', '.pyo'):
                yield path


def build(output):
    version = json.loads((ROOT / 'plugins/ai-learning-companion/plugin.json').read_text())['version']
    output.mkdir(parents=True, exist_ok=True)
    archive = output / ('ai-learning-companion-' + version + '-macos.zip')
    manifest = {}
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for path in files():
            relative = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            if Path.home().as_posix().encode() in data:
                raise ValueError('Machine-specific data in release: ' + relative)
            if relative == 'plugins/ai-learning-companion/config.json':
                cfg = json.loads(data)
                if cfg.get('data_root') is not None:
                    raise ValueError('Release config must not contain a personal data_root')
            manifest[relative] = hashlib.sha256(data).hexdigest()
            info = zipfile.ZipInfo('ai-learning-companion/' + relative, date_time=(2026, 10, 9, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if relative == 'Install.command' else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            zipped.writestr(info, data)
        payload = json.dumps({'version': version, 'platform': 'macOS', 'files': manifest}, ensure_ascii=False, indent=2).encode()
        info = zipfile.ZipInfo('ai-learning-companion/RELEASE-MANIFEST.json', date_time=(2026, 10, 9, 0, 0, 0))
        info.create_system = 3
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        zipped.writestr(info, payload)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum_file = output / (archive.name + '.sha256')
    checksum_file.write_text(checksum + '  ' + archive.name + '\n')
    result = {'ok': True, 'version': version, 'archive': str(archive), 'sha256': checksum,
              'checksum_file': str(checksum_file), 'files_count': len(manifest), 'bytes': archive.stat().st_size}
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), ensure_ascii=False))
