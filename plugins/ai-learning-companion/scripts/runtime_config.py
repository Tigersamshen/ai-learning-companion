"""User-owned runtime settings, kept outside the installed plugin cache."""
import json
import os
from pathlib import Path
import tempfile

PLUGIN = Path(__file__).resolve().parents[1]


def config_path():
    override = os.environ.get('AI_LEARNING_CONFIG')
    return Path(override).expanduser().resolve() if override else Path.home() / 'Library' / 'Application Support' / 'ai-learning-companion' / 'config.json'


def resolve_data_root(explicit=None):
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    if os.environ.get('AI_LEARNING_ROOT'):
        return Path(os.environ['AI_LEARNING_ROOT']).expanduser().resolve()
    settings = config_path()
    if settings.exists():
        value = json.loads(settings.read_text(encoding='utf-8'))
        if not value.get('data_root'):
            raise ValueError('用户配置缺少 data_root；请重新运行安装初始化')
        return Path(value['data_root']).expanduser().resolve()
    legacy = PLUGIN / 'config.json'
    if legacy.exists():
        value = json.loads(legacy.read_text(encoding='utf-8'))
        if value.get('data_root'):
            return Path(value['data_root']).expanduser().resolve()
    return Path.home() / 'Documents' / 'AI学习助手'


def write_user_config(data_root, allow_switch=False):
    target = config_path()
    root = Path(data_root).expanduser().resolve()
    value = {}
    if target.exists():
        value = json.loads(target.read_text(encoding='utf-8'))
        previous = value.get('data_root')
        if previous and Path(previous).expanduser().resolve() != root and not allow_switch:
            raise ValueError('已有数据目录不同；请显式指定 --data-root 后再切换，原数据不会迁移或删除')
        if previous and Path(previous).expanduser().resolve() == root:
            return target
    value.update(version=1, data_root=str(root))
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.learning-config-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write('\n')
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target
