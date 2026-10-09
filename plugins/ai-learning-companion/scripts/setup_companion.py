#!/usr/bin/env python3
"""从解压包准备独立学习目录；仅 --install 调用官方 Codex 安装命令。"""

import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from diagram_renderer import _chrome_path
from runtime_config import config_path, resolve_data_root, write_user_config


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_ROOT = PLUGIN_ROOT / "assets" / "templates" / "learning-vault"
PLUGIN_NAME = "ai-learning-companion"
MARKETPLACE_NAME = "ai-learning-companion"


class SetupError(ValueError):
    def __init__(self, message, code="setup_failed", details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise SetupError(message, "invalid_arguments")


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".companion-setup-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def executable(path):
    return bool(path and Path(path).is_file() and os.access(path, os.X_OK))


def codex_path():
    """优先 PATH；仅使用实际发现的官方 app bundle 内可执行文件。"""
    found = shutil.which("codex")
    if executable(found):
        return str(Path(found).resolve())
    application_roots = (Path("/Applications"), Path.home() / "Applications", Path.home() / "Desktop")
    for application_root in application_roots:
        for app_name in ("Codex.app", "Codex Alpha.app", "Codex Beta.app", "ChatGPT.app"):
            bundle = application_root / app_name
            for relative in ("Contents/Resources/codex", "Contents/Resources/bin/codex",
                             "Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"):
                candidate = bundle / relative
                if executable(candidate):
                    return str(candidate.resolve())
    return None


def obsidian_registry_path():
    return Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"


def registered_vault(vault_path):
    """只认 Obsidian 自己登记的完整路径；不根据 Vault 名称猜测 ID。"""
    registry = obsidian_registry_path()
    if not registry.exists():
        return None
    try:
        value = json.loads(registry.read_text(encoding="utf-8"))
        vaults = value.get("vaults", {})
        if not isinstance(vaults, dict):
            raise ValueError("vaults 不是对象")
        desired = Path(vault_path).resolve()
        matches = []
        for vault_id, entry in vaults.items():
            path = entry.get("path") if isinstance(entry, dict) else None
            if not isinstance(path, str) or not Path(path).is_absolute():
                continue
            if Path(path).resolve() == desired:
                matches.append(vault_id)
        if len(matches) > 1:
            raise ValueError("同一学习目录登记了多个 Vault ID，请先在 Obsidian 中整理")
        return matches[0] if matches else None
    except (OSError, ValueError, AttributeError) as error:
        raise SetupError("无法读取 Obsidian 仓库登记：" + str(error), "vault_registry_invalid",
                         {"registry": str(registry)}) from error


def dependencies():
    try:
        chrome = {"available": True, "path": _chrome_path()}
    except (ValueError, OSError) as error:
        chrome = {"available": False, "path": None, "message": str(error)}
    codex = codex_path()
    obsidian = shutil.which("obsidian")
    return {
        "python": {"available": sys.version_info >= (3, 10), "path": sys.executable,
                   "version": ".".join(str(part) for part in sys.version_info[:3]),
                   "required": "3.10+"},
        "codex": {"available": bool(codex), "path": codex},
        "chrome": chrome,
        "obsidian_cli": {"available": executable(obsidian), "path": obsidian},
    }


def initialize_data(root):
    """只补缺失的模板文件；用户编辑的笔记和 Obsidian 配置原样保留。"""
    root = Path(root).resolve()
    vault = root / "学习笔记库"
    if vault.is_symlink():
        raise SetupError("学习笔记库为符号链接，请选择独立的数据目录。", "unsafe_vault_path",
                         {"vault_path": str(vault)})
    if not TEMPLATE_ROOT.is_dir():
        raise SetupError("安装包缺少空白笔记库模板。", "template_missing",
                         {"template_path": str(TEMPLATE_ROOT)})
    (root / "state").mkdir(parents=True, exist_ok=True)
    (vault / "主题").mkdir(parents=True, exist_ok=True)
    created, preserved = [], []
    for source in sorted(TEMPLATE_ROOT.rglob("*")):
        relative = source.relative_to(TEMPLATE_ROOT)
        target = vault / relative
        if source.is_symlink():
            raise SetupError("安装包模板不得包含符号链接。", "invalid_template")
        if source.is_dir():
            if target.is_symlink():
                raise SetupError("已有模板目录为符号链接，停止写入。", "unsafe_vault_path",
                                 {"path": str(target)})
            target.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            if target.exists() or target.is_symlink():
                preserved.append(str(target))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if vault.resolve() not in target.parent.resolve().parents and target.parent.resolve() != vault.resolve():
                raise SetupError("模板写入路径越出学习笔记库。", "unsafe_vault_path")
            try:
                with target.open("xb") as output:
                    output.write(source.read_bytes())
                created.append(str(target))
            except FileExistsError:
                preserved.append(str(target))
    return {"created_files": created, "preserved_files": preserved}


def vault_report(root, checks):
    vault = Path(root) / "学习笔记库"
    report = {"vault_path": str(vault), "registry": str(obsidian_registry_path()),
              "registered_vault_id": None, "configured_vault_id": None, "ready": False}
    try:
        report["registered_vault_id"] = registered_vault(vault)
        deployment_path = Path(root) / "deployment.json"
        if deployment_path.exists():
            deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
            if (isinstance(deployment, dict)
                    and deployment.get("vault_path") == str(vault.resolve())):
                report["configured_vault_id"] = deployment.get("vault_id")
        report["ready"] = bool(checks["obsidian_cli"]["available"]
                               and report["registered_vault_id"]
                               and report["registered_vault_id"] == report["configured_vault_id"])
    except (SetupError, OSError, ValueError) as error:
        report["message"] = str(error)
    if not report["registered_vault_id"]:
        report["next_steps"] = [
            "打开 Obsidian，选择“管理仓库”→“打开文件夹作为仓库”。",
            "选择此文件夹：" + str(vault),
            "完成后重复运行 setup_companion.py --data-root <上面的数据根目录> --register-vault。",
        ]
    elif not report["configured_vault_id"]:
        report["next_steps"] = ["重复运行 setup_companion.py --register-vault，保存 Obsidian 的真实 Vault ID。"]
    elif not checks["obsidian_cli"]["available"]:
        report["next_steps"] = ["在 Obsidian 设置中启用命令行界面，将 obsidian 命令加入 PATH，然后重新运行 --check。"]
    return report


def register_vault(root):
    vault = (Path(root) / "学习笔记库").resolve()
    vault_id = registered_vault(vault)
    if not vault_id:
        raise SetupError("此学习笔记库尚未在 Obsidian 登记。请先在界面中打开该文件夹，再运行 --register-vault。",
                         "vault_unregistered", {"vault_path": str(vault),
                                                "registry": str(obsidian_registry_path())})
    path = Path(root) / "deployment.json"
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as error:
            raise SetupError("已有 deployment.json 无法读取；保留文件并停止。",
                             "deployment_invalid", {"deployment": str(path)}) from error
        if not isinstance(existing, dict):
            raise SetupError("已有 deployment.json 不是对象；保留文件并停止。", "deployment_invalid")
    value = dict(existing, vault_id=vault_id, vault_path=str(vault), registration="Obsidian UI")
    if (existing.get("vault_id") != vault_id or existing.get("vault_path") != str(vault)
            or "registered_at" not in existing):
        value["registered_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if value != existing:
        atomic_json(path, value)
    return {"deployment": str(path), "vault_id": vault_id, "vault_path": str(vault)}


def _cli_output(output):
    text = (output or "").strip()
    try:
        return json.loads(text) if text else None
    except ValueError:
        return text


def install_plugin(package_root, codex):
    if not codex:
        raise SetupError("未找到官方 codex CLI；请安装 Codex CLI 或将其加入 PATH，然后重试 --install。",
                         "codex_missing")
    package_root = Path(package_root).expanduser().resolve()
    manifest = package_root / ".agents" / "plugins" / "marketplace.json"
    try:
        catalog = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SetupError("安装包的独立插件目录无效：" + str(error), "marketplace_invalid",
                         {"marketplace_manifest": str(manifest)}) from error
    entries = catalog.get("plugins", []) if isinstance(catalog, dict) else []
    if (not isinstance(catalog, dict) or catalog.get("name") != MARKETPLACE_NAME
            or not isinstance(entries, list)
            or not any(isinstance(item, dict) and item.get("name") == PLUGIN_NAME
                       for item in entries)):
        raise SetupError("安装包必须使用 ai-learning-companion 独立插件目录；不会修改 personal 目录。",
                         "marketplace_invalid", {"marketplace_manifest": str(manifest)})
    operations = [
        ("marketplace_add", [codex, "plugin", "marketplace", "add", str(package_root)]),
        ("plugin_add", [codex, "plugin", "add", PLUGIN_NAME + "@" + MARKETPLACE_NAME, "--json"]),
    ]
    results = []
    for stage, command in operations:
        try:
            process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=60)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SetupError("官方 Codex 安装命令未完成：" + str(error), "install_failed",
                             {"stage": stage, "command": command}) from error
        output = {"stage": stage, "command": command, "exit_code": process.returncode,
                  "output": _cli_output(process.stdout)}
        results.append(output)
        if process.returncode:
            raise SetupError("官方 Codex 安装命令失败。", "install_failed",
                             {"stage": stage, "command": command, "exit_code": process.returncode,
                              "stdout": process.stdout.strip(), "stderr": process.stderr.strip()})
    return {"package_root": str(package_root), "marketplace": MARKETPLACE_NAME,
            "plugin": PLUGIN_NAME + "@" + MARKETPLACE_NAME, "operations": results}


def parser():
    value = JsonArgumentParser(description=__doc__)
    value.add_argument("--data-root", type=Path, help="独立数据目录；默认读取用户配置。")
    value.add_argument("--interactive", action="store_true", help="显式询问数据目录。")
    value.add_argument("--install", action="store_true", help="通过官方 Codex CLI 安装独立插件。")
    value.add_argument("--register-vault", action="store_true", help="读取 Obsidian 实际登记并保存部署信息。")
    value.add_argument("--check", action="store_true", help="只读检查路径与运行依赖。")
    value.add_argument("--package-root", type=Path, default=PACKAGE_ROOT, help="包含 plugins 的解压包根目录。")
    return value


def run(arguments):
    if arguments.check and (arguments.install or arguments.register_vault or arguments.interactive):
        raise SetupError("--check 为只读模式，请与安装、登记或交互操作分开运行。", "invalid_arguments")
    explicit = arguments.data_root
    if arguments.interactive and explicit is None:
        suggested = resolve_data_root()
        try:
            print("学习数据目录（回车使用 " + str(suggested) + "）：", end="", file=sys.stderr, flush=True)
            answer = input().strip()
        except EOFError as error:
            raise SetupError("交互模式未收到输入；请使用 --data-root 指定目录。", "input_unavailable") from error
        explicit = Path(answer).expanduser() if answer else None
    root = resolve_data_root(explicit)
    checks = dependencies()
    result = {"ok": True, "check_only": arguments.check, "data_root": str(root),
              "user_config": str(config_path()), "package_root": str(arguments.package_root.expanduser().resolve()),
              "dependencies": checks, "basic_runtime_ready": checks["python"]["available"]}
    if not checks["python"]["available"]:
        raise SetupError("需要 Python 3.10 或更新版本。", "python_version", result)
    if arguments.check:
        result["vault"] = vault_report(root, checks)
        return result
    if arguments.install and not checks["codex"]["available"]:
        raise SetupError("未找到官方 codex CLI；请先安装或加入 PATH，然后重试 --install。", "codex_missing", result)
    result["initialization"] = initialize_data(root)
    result["user_config"] = str(write_user_config(root, allow_switch=explicit is not None))
    if arguments.install:
        result["installation"] = install_plugin(arguments.package_root, checks["codex"]["path"])
    if arguments.register_vault:
        try:
            result["registration"] = register_vault(root)
        except SetupError as error:
            result.update(ok=False, error=str(error), code=error.code, details=error.details)
    result["vault"] = vault_report(root, checks)
    return result


def main(argv=None):
    try:
        result = run(parser().parse_args(argv))
    except (SetupError, ValueError, OSError) as error:
        result = {"ok": False, "error": str(error), "code": getattr(error, "code", "setup_failed"),
                  "details": getattr(error, "details", {})}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
