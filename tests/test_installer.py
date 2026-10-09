"""Portable installer acceptance tests; only temporary user files are mutated.

Codex installation commands are mocked. No test installs a plugin, launches
Obsidian, or changes the developer's existing Vault/catalog/configuration.
"""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


PROJECT = Path(__file__).resolve().parents[1]
PLUGIN = PROJECT / "plugins" / "ai-learning-companion"
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))
import setup_companion as setup


class PortableInstallerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="companion-installer-test-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.root = self.home / "学习数据"
        self.configuration = self.home / "Application Support" / "companion" / "config.json"
        self.registry = self.home / "Obsidian" / "obsidian.json"
        self.package = self.home / "解压安装包"
        manifest = self.package / ".agents" / "plugins" / "marketplace.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"name": "ai-learning-companion", "plugins": [
            {"name": "ai-learning-companion", "source": {"source": "local", "path": "./plugins/ai-learning-companion"}}
        ]}), encoding="utf-8")
        environment = mock.patch.dict(os.environ, {"AI_LEARNING_CONFIG": str(self.configuration),
                                                   "AI_LEARNING_ROOT": ""}, clear=False)
        environment.start()
        self.addCleanup(environment.stop)
        home = mock.patch.object(Path, "home", return_value=self.home)
        home.start()
        self.addCleanup(home.stop)
        registry = mock.patch.object(setup, "obsidian_registry_path", return_value=self.registry)
        registry.start()
        self.addCleanup(registry.stop)
        self.dependency_values = {
            "python": {"available": True, "path": sys.executable, "version": "3.10.1", "required": "3.10+"},
            "codex": {"available": False, "path": None},
            "chrome": {"available": False, "path": None},
            "obsidian_cli": {"available": False, "path": None},
        }
        dependencies = mock.patch.object(setup, "dependencies", return_value=self.dependency_values)
        dependencies.start()
        self.addCleanup(dependencies.stop)

    def run_setup(self, *arguments, ok=True):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            exit_code = setup.main(list(arguments))
        result = json.loads(stream.getvalue())
        self.assertEqual(result["ok"], ok, result)
        self.assertEqual(exit_code, 0 if ok else 1, result)
        return result

    def register(self, value):
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        self.registry.write_text(json.dumps({"vaults": value}), encoding="utf-8")

    def test_fresh_path_and_separate_user_config_need_no_optional_dependencies(self):
        plugin_config = PLUGIN / "config.json"
        original = plugin_config.read_bytes()
        with mock.patch("builtins.input", side_effect=AssertionError("implicit input")):
            result = self.run_setup("--data-root", str(self.root))
        self.assertTrue((self.root / "state").is_dir())
        self.assertEqual(list((self.root / "state").iterdir()), [])
        vault = self.root / "学习笔记库"
        self.assertTrue((vault / "主题").is_dir())
        self.assertEqual(list((vault / "主题").iterdir()), [])
        self.assertTrue((vault / "欢迎.md").is_file())
        self.assertFalse((self.root / "deployment.json").exists())
        self.assertEqual(json.loads(self.configuration.read_text())["data_root"], str(self.root))
        self.assertEqual(plugin_config.read_bytes(), original)
        self.assertTrue(result["basic_runtime_ready"])
        self.assertFalse(result["vault"]["ready"])
        self.assertTrue(result["vault"]["next_steps"])

    def test_rerun_preserves_manual_notes_and_obsidian_configuration(self):
        self.run_setup("--data-root", str(self.root))
        welcome = self.root / "学习笔记库" / "欢迎.md"
        obsidian = self.root / "学习笔记库" / ".obsidian" / "app.json"
        welcome.write_text("# 我的人工修改\n", encoding="utf-8")
        obsidian.write_text('{"user_preference": true}\n', encoding="utf-8")
        config_before = self.configuration.read_bytes()
        result = self.run_setup()
        self.assertEqual(welcome.read_text(encoding="utf-8"), "# 我的人工修改\n")
        self.assertEqual(obsidian.read_text(), '{"user_preference": true}\n')
        self.assertEqual(self.configuration.read_bytes(), config_before)
        self.assertEqual(result["initialization"]["created_files"], [])
        self.assertIn(str(welcome), result["initialization"]["preserved_files"])

    def test_check_is_read_only_even_for_missing_data_and_config(self):
        result = self.run_setup("--data-root", str(self.root), "--check")
        self.assertTrue(result["check_only"])
        self.assertFalse(self.root.exists())
        self.assertFalse(self.configuration.exists())
        self.assertFalse(self.registry.exists())
        with mock.patch("builtins.input", side_effect=AssertionError("read-only input")):
            self.run_setup("--check", "--interactive", ok=False)
        invalid = self.run_setup("--does-not-exist", ok=False)
        self.assertEqual(invalid["code"], "invalid_arguments")
        self.assertFalse(self.configuration.exists())

    def test_explicit_location_and_interactive_choice_can_switch_user_config(self):
        self.run_setup("--data-root", str(self.root))
        alternate = self.home / "新的学习数据"
        self.run_setup("--data-root", str(alternate))
        self.assertEqual(json.loads(self.configuration.read_text())["data_root"], str(alternate))
        with mock.patch("builtins.input", return_value=str(self.root)) as answer:
            self.run_setup("--interactive")
        answer.assert_called_once_with()
        self.assertEqual(json.loads(self.configuration.read_text())["data_root"], str(self.root))
        self.assertTrue(alternate.is_dir())

    def test_vault_registration_matches_actual_full_path_and_is_idempotent(self):
        self.run_setup("--data-root", str(self.root))
        self.register({
            "same-name-wrong-folder": {"path": str(self.home / "other" / "学习笔记库")},
            "actual-vault-id": {"path": str(self.root / "学习笔记库")},
        })
        self.dependency_values["obsidian_cli"] = {"available": True, "path": "/mock/obsidian"}
        result = self.run_setup("--register-vault")
        self.assertEqual(result["registration"]["vault_id"], "actual-vault-id")
        self.assertTrue(result["vault"]["ready"])
        deployment = self.root / "deployment.json"
        value = json.loads(deployment.read_text())
        value["manual_note"] = "保留自定义字段"
        deployment.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
        before = deployment.read_bytes()
        self.run_setup("--register-vault")
        self.assertEqual(deployment.read_bytes(), before)

    def test_unregistered_vault_never_fabricates_deployment_id(self):
        self.register({"other-id": {"path": str(self.home / "other" / "学习笔记库")}})
        result = self.run_setup("--data-root", str(self.root), "--register-vault", ok=False)
        self.assertEqual(result["code"], "vault_unregistered")
        self.assertFalse((self.root / "deployment.json").exists())
        self.assertFalse(result["vault"]["ready"])
        self.assertTrue(result["vault"]["next_steps"])

    def test_missing_codex_explicit_install_errors_without_external_calls(self):
        with mock.patch.object(setup.subprocess, "run") as process:
            result = self.run_setup("--data-root", str(self.root), "--install", ok=False)
        self.assertEqual(result["code"], "codex_missing")
        process.assert_not_called()
        self.assertFalse(self.configuration.exists())
        self.assertFalse(self.root.exists())

    def test_official_cli_install_preserves_personal_catalog_and_uses_own_marketplace(self):
        personal = self.home / ".codex" / "marketplaces" / "personal" / ".agents" / "plugins" / "marketplace.json"
        personal.parent.mkdir(parents=True)
        original = b'{"name":"personal","plugins":[{"name":"unrelated"}]}\n'
        personal.write_bytes(original)
        self.dependency_values["codex"] = {"available": True, "path": "/mock/codex"}
        responses = [subprocess.CompletedProcess([], 0, "Marketplace added\n", ""),
                     subprocess.CompletedProcess([], 0, '{"installed":true}', "")]
        with mock.patch.object(setup.subprocess, "run", side_effect=responses) as process:
            result = self.run_setup("--data-root", str(self.root), "--install", "--package-root", str(self.package))
        self.assertEqual(process.call_args_list[0].args[0],
                         ["/mock/codex", "plugin", "marketplace", "add", str(self.package)])
        self.assertEqual(process.call_args_list[1].args[0],
                         ["/mock/codex", "plugin", "add", "ai-learning-companion@ai-learning-companion", "--json"])
        self.assertEqual(personal.read_bytes(), original)
        self.assertEqual(result["installation"]["operations"][1]["output"], {"installed": True})

    def test_cli_failure_reports_stage_and_stops_before_next_mutation(self):
        self.dependency_values["codex"] = {"available": True, "path": "/mock/codex"}
        with mock.patch.object(setup.subprocess, "run", return_value=
                               subprocess.CompletedProcess([], 2, "", "catalog unavailable")) as process:
            result = self.run_setup("--data-root", str(self.root), "--install", "--package-root", str(self.package), ok=False)
        self.assertEqual(process.call_count, 1)
        self.assertEqual(result["code"], "install_failed")
        self.assertEqual(result["details"]["stage"], "marketplace_add")
        self.assertEqual(result["details"]["stderr"], "catalog unavailable")
        self.assertFalse((self.root / "deployment.json").exists())

    def test_codex_gui_path_fallback_requires_discovered_executable_bundle(self):
        candidate = self.home / "Applications" / "ChatGPT.app" / "Contents" / "Resources" / "codex-cli" / "CodexCLI.app" / "Contents" / "MacOS" / "codex"
        real_executable = setup.executable
        with mock.patch.object(setup.shutil, "which", return_value=None), \
                mock.patch.object(setup, "executable", side_effect=lambda path:
                                  real_executable(path) if path and Path(path) == candidate else False):
            self.assertIsNone(setup.codex_path())
            candidate.parent.mkdir(parents=True)
            candidate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            self.assertIsNone(setup.codex_path())
            candidate.chmod(0o700)
            self.assertEqual(setup.codex_path(), str(candidate))


if __name__ == "__main__":
    unittest.main()
