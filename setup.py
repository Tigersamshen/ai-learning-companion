#!/usr/bin/env python3
"""Portable entry point; selects a supported installed Python when needed."""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
if sys.version_info < (3, 10):
    candidates = [shutil.which('python3.' + str(v)) for v in range(14, 9, -1)]
    candidates += [str(p) for p in (Path.home() / '.cache/codex-runtimes').glob('*/dependencies/python/bin/python3')]
    candidates += ['/opt/homebrew/bin/python3', '/usr/local/bin/python3']
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file() or Path(candidate).resolve() == Path(sys.executable).resolve():
            continue
        try:
            check = subprocess.run([candidate, '-c', 'import sys;raise SystemExit(sys.version_info<(3,10))'], capture_output=True, timeout=8)
            if check.returncode == 0:
                os.execv(candidate, [candidate, str(ROOT / 'setup.py'), *sys.argv[1:]])
        except OSError:
            continue
    print(json.dumps({'ok': False, 'error': '需要 Python 3.10+；请安装受支持的 Python 后重试。', 'code': 'python_version'}, ensure_ascii=False))
    raise SystemExit(1)
sys.path.insert(0, str(ROOT / 'plugins/ai-learning-companion/scripts'))
sys.argv[0] = str(ROOT / 'plugins/ai-learning-companion/scripts/setup_companion.py')
runpy.run_path(sys.argv[0], run_name='__main__')
