"""标准库渲染校验；RUN_RENDER_INTEGRATION=1 可运行真实离线 Chrome。"""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "ai-learning-companion" / "scripts" / "diagram_renderer.py"
SPEC = importlib.util.spec_from_file_location("diagram_renderer", SCRIPT)
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)

DAG = """flowchart LR
    A[收集学习素材] --> B[提炼核心思想]
    B --> C[连接已有笔记]
    C --> D[形成可执行实验]
    D --> E[复盘并更新理解]
"""
LONG_LABELS = """flowchart TB
    A[从视频、文章和项目记录中收集原始素材，并保留可追溯的来源] --> B[用自己的话解释关键观点，明确适用条件和反例]
    B --> C[把观点变成具体练习，通过真实任务检验它是否有效]
    C --> D[记录实际结果与失败原因，修订知识卡并链接相关笔记]
"""
MINDMAP = """mindmap
  root((持续学习))
    输入
      视频与文章
      项目经验
    理解
      核心思想
      适用条件
    应用
      设计实验
      收集反馈
    沉淀
      知识卡片
      主题双链
"""
SELF_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 220">
  <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#566573"/></marker></defs>
  <rect x="20" y="60" width="180" height="80" rx="14" fill="#eef6ff" stroke="#3572a5"/>
  <rect x="230" y="60" width="180" height="80" rx="14" fill="#f0f8ed" stroke="#527a39"/>
  <rect x="440" y="60" width="180" height="80" rx="14" fill="#fff4e6" stroke="#ad7333"/>
  <path d="M200,100 L224,100" stroke="#566573" stroke-width="2" marker-end="url(#arrow)"/>
  <path d="M410,100 L434,100" stroke="#566573" stroke-width="2" marker-end="url(#arrow)"/>
  <g text-anchor="middle" fill="#1c2833" font-size="22"><text x="110" y="108">理解观点</text><text x="320" y="108">动手实践</text><text x="530" y="108">更新知识</text></g>
  <text x="320" y="190" text-anchor="middle" fill="#566573" font-size="16">离线 SVG：中文标签、图形与内部标记</text>
</svg>"""


class RendererValidationTests(unittest.TestCase):
    def test_svg_dimensions_and_internal_marker(self):
        self.assertEqual(renderer._validate_svg(SELF_SVG), (640, 220))

    def test_rejects_script_remote_image_event_and_css_import(self):
        unsafe = [
            '<script>alert(1)</script>',
            '<image href="https://example.com/image.png"/>',
            '<image href="file:///etc/passwd"/>',
            '<rect onload="alert(1)"/>',
            '<style>@import "https://example.com/font.css";</style>',
            '<rect style="fill:url(https://example.com/image.png)"/>',
            '<foreignObject><iframe xmlns="http://www.w3.org/1999/xhtml" src="https://example.com"/></foreignObject>',
        ]
        for body in unsafe:
            with self.subTest(body=body), self.assertRaises(ValueError):
                renderer._validate_svg('<svg xmlns="' + renderer.SVG_NS + '" viewBox="0 0 100 100">' + body + '</svg>')

    def test_rejects_missing_negative_nonfinite_and_excessive_dimensions(self):
        for attributes in ('', 'viewBox="0 0 -1 100"', 'viewBox="0 0 nan 100"', 'viewBox="0 0 100000 100"'):
            with self.subTest(attributes=attributes), self.assertRaises(ValueError):
                renderer._validate_svg('<svg ' + attributes + '/>')

    def test_rejects_mermaid_urls_before_chrome(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "unsafe.mmd"
            source.write_text('flowchart LR\n A@{img: "https://example.com/image.png"}', encoding="utf-8")
            with mock.patch.object(renderer, "_run_chrome") as launch:
                with self.assertRaises(renderer.DiagramRenderError) as caught:
                    renderer.render_diagram(source, "mermaid", Path(temporary) / "output")
            launch.assert_not_called()
            result = caught.exception.result
            self.assertEqual(result["status"], "failed")
            self.assertNotIn("png", result)
            self.assertEqual(json.loads(Path(result["log"]).read_text())["status"], "failed")

    def test_failed_chrome_writes_log_and_never_reports_rendered(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "diagram.svg"
            source.write_text(SELF_SVG, encoding="utf-8")
            with mock.patch.object(renderer, "_run_chrome", side_effect=ValueError("模拟 Chrome 超时")):
                with self.assertRaises(renderer.DiagramRenderError) as caught:
                    renderer.render_diagram(source, "svg", Path(temporary) / "output")
            self.assertEqual(caught.exception.result["status"], "failed")
            self.assertIn("超时", Path(caught.exception.result["log"]).read_text())
            self.assertEqual(source.read_text(encoding="utf-8"), SELF_SVG)

    def test_refuses_output_collision(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "diagram.svg"
            source.write_text(SELF_SVG, encoding="utf-8")
            output = directory / "output"
            output.mkdir()
            existing = output / "diagram.png"
            existing.write_bytes(b"keep existing")
            existing_log = output / "diagram.render.json"
            existing_log.write_text("keep original log", encoding="utf-8")
            with self.assertRaises(renderer.DiagramRenderError) as caught:
                renderer.render_diagram(source, "svg", output)
            self.assertEqual(existing.read_bytes(), b"keep existing")
            self.assertEqual(existing_log.read_text(encoding="utf-8"), "keep original log")
            self.assertNotEqual(caught.exception.result["log"], str(existing_log))

    def test_same_directory_svg_input_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "diagram.svg"
            source.write_text(SELF_SVG, encoding="utf-8")
            with mock.patch.object(renderer, "_run_chrome", side_effect=ValueError("模拟 Chrome 失败")):
                with self.assertRaises(renderer.DiagramRenderError):
                    renderer.render_diagram(source, "svg", directory)
            self.assertEqual(source.read_text(encoding="utf-8"), SELF_SVG)
            self.assertTrue((directory / "diagram.rendered.svg").is_file())

    def test_truncated_png_is_not_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "partial.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR" + b"\x00\x00\x00\x64" * 2)
            self.assertEqual(renderer._png_dimensions(path), (100, 100))
            self.assertFalse(renderer._complete_png(path))

    def test_rejects_path_in_stem(self):
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(ValueError):
            renderer.render_diagram("anything", "svg", temporary, "../escape")


@unittest.skipUnless(os.environ.get("RUN_RENDER_INTEGRATION") == "1", "设置 RUN_RENDER_INTEGRATION=1 运行真实 Chrome")
class RendererChromeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        renderer._chrome_path()
        cls.temporary = None
        if os.environ.get("RENDER_TEST_OUTPUT_DIR"):
            cls.directory = Path(os.environ["RENDER_TEST_OUTPUT_DIR"]).resolve()
            cls.directory.mkdir(parents=True, exist_ok=True)
        else:
            cls.temporary = tempfile.TemporaryDirectory(prefix="renderer-verification-")
            cls.directory = Path(cls.temporary.name)
        cls.sources = cls.directory / "inputs"
        cls.sources.mkdir(exist_ok=True)
        cls.records = []

    @classmethod
    def tearDownClass(cls):
        report = {"network_mode": "Chrome HTTP/HTTPS proxy and DNS denied; local file rendering only", "visual_verified": False, "records": cls.records}
        (cls.directory / "renderer-test-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if cls.temporary:
            cls.temporary.cleanup()

    def _render(self, name, definition, kind="mermaid"):
        source = self.sources / (name + (".svg" if kind == "svg" else ".mmd"))
        source.write_text(definition, encoding="utf-8")
        try:
            result = renderer.render_diagram(source, kind, self.directory, name)
            self.records.append({"case": name, "status": "passed", "result": result})
        except renderer.DiagramRenderError as exc:
            self.records.append({"case": name, "status": "failed", "result": exc.result})
            raise
        self.assertEqual(result["status"], "rendered")
        self.assertFalse(result["visual_verified"])
        for key in ("source", "svg", "png", "preview", "log"):
            self.assertTrue(Path(result[key]).is_file(), key)
        self.assertEqual(renderer._png_dimensions(Path(result["png"])), (result["width"], result["height"]))
        self.assertEqual(source.read_text(encoding="utf-8"), definition)
        log = json.loads(Path(result["log"]).read_text())
        self.assertEqual(log["status"], "rendered")
        for event in log["events"]:
            if event["stage"] == "chrome":
                self.assertIn("--proxy-server=http://127.0.0.1:9", event["command"])
                self.assertIn("--host-resolver-rules=MAP * ~NOTFOUND", event["command"])
        return result

    def test_chinese_dag(self):
        result = self._render("chinese-dag", DAG)
        self.assertIn("收集学习素材", Path(result["svg"]).read_text(encoding="utf-8"))

    def test_long_labels(self):
        self._render("long-labels", LONG_LABELS)

    def test_line_break_labels_produce_valid_xml(self):
        result = self._render("line-break", 'flowchart TD\n A["列表与索引<br/>保留先修关系"] --> B["遍历与汇总"]')
        self.assertIn("保留先修关系", Path(result["svg"]).read_text(encoding="utf-8"))

    def test_mindmap(self):
        self._render("mindmap", MINDMAP)

    def test_self_svg(self):
        self._render("self-svg", SELF_SVG, "svg")

    def test_offline_render(self):
        result = self._render("offline", "flowchart LR\n A[离线来源] --> B[本地 Mermaid] --> C[本机 Chrome PNG]")
        log = json.loads(Path(result["log"]).read_text())
        stages = [event["stage"] for event in log["events"]]
        self.assertEqual(stages, ["chrome", "mermaid", "svg", "chrome", "png"])
        preview = Path(result["preview"]).read_text(encoding="utf-8")
        self.assertNotIn("<script", preview)
        self.assertIn("connect-src 'none'", preview)

    def test_invalid_mermaid_has_no_success_or_png(self):
        source = self.sources / "invalid.mmd"
        source.write_text("flowchart LR\n A[未闭合的标签 --> B", encoding="utf-8")
        with self.assertRaises(renderer.DiagramRenderError) as caught:
            renderer.render_diagram(source, "mermaid", self.directory, "invalid")
        result = caught.exception.result
        self.assertEqual(result["status"], "failed")
        self.assertIn("语法", result["error"])
        self.assertFalse((self.directory / "invalid.png").exists())
        self.records.append({"case": "invalid-syntax", "status": "passed", "expected_failure": result})


if __name__ == "__main__":
    unittest.main()
