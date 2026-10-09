#!/usr/bin/env python3
"""离线 Mermaid/SVG 渲染：仅 Python 标准库、本地 Mermaid 和 Chrome。"""

import argparse
import base64
import datetime
import hashlib
import html
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
VENDOR_PATH = PLUGIN_ROOT / "assets" / "vendor" / "mermaid.min.js"
CHROME_MAC = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
TIMEOUT_SECONDS = 35
MAX_SOURCE_BYTES = 256_000
MAX_SIDE = 8192
MAX_PIXELS = 32_000_000
SVG_NS = "http://www.w3.org/2000/svg"
XHTML_NS = "http://www.w3.org/1999/xhtml"
FONT = "'PingFang SC', 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif"
CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; font-src 'none'; connect-src 'none'; object-src 'none'; "
    "base-uri 'none'; form-action 'none'"
)
REMOTE_URL = re.compile(r"(?:https?|ftp|file|javascript):|(?<!:)//", re.I)
CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I | re.S)
SVG_TAGS = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline",
    "polygon", "text", "tspan", "defs", "marker", "pattern", "linearGradient",
    "radialGradient", "stop", "clipPath", "mask", "use", "style", "title",
    "desc", "foreignObject", "image", "switch", "symbol", "filter",
    "feGaussianBlur", "feOffset", "feBlend", "feColorMatrix", "feFlood",
    "feComposite", "feMerge", "feMergeNode", "feDropShadow",
}
HTML_TAGS = {"div", "span", "p", "br", "b", "strong", "em", "i"}


class DiagramRenderError(RuntimeError):
    """失败时 result 保留日志路径，不把部分产物声明为渲染完成。"""

    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


class _ResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.payload = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and values.get("name") == "diagram-render-result":
            self.payload = values.get("content")


def _chrome_path():
    configured = os.environ.get("DIAGRAM_CHROME_PATH")
    candidates = [configured] if configured else [str(CHROME_MAC)]
    candidates += [shutil.which(name) for name in (
        "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"
    )]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise ValueError("未找到 Chrome；可通过 DIAGRAM_CHROME_PATH 指定可执行文件。")


def _validate_css(text):
    if re.search(r"@import|expression\s*\(|(?:https?|ftp|file|javascript):|//", text, re.I):
        raise ValueError("SVG 样式不允许外部资源、导入或脚本。")
    for match in CSS_URL.finditer(text):
        if not match.group(2).strip().startswith("#"):
            raise ValueError("SVG 样式仅允许引用本图内部的 #id。")


def _validate_svg(text):
    if re.search(r"<!DOCTYPE|<!ENTITY|<\?xml-stylesheet", text, re.I):
        raise ValueError("SVG 不允许 DTD、实体或外部样式表。")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError("SVG XML 无法解析：" + str(exc)) from exc
    if root.tag not in ("svg", "{" + SVG_NS + "}svg"):
        raise ValueError("输入的根元素必须是 SVG。")
    for element in root.iter():
        namespace, _, local = element.tag[1:].partition("}") if element.tag.startswith("{") else ("", "", element.tag)
        if namespace in ("", SVG_NS):
            allowed = local in SVG_TAGS
        else:
            allowed = namespace == XHTML_NS and local in HTML_TAGS
        if not allowed:
            raise ValueError("SVG 包含不支持或不安全的元素：" + local)
        if local == "style":
            _validate_css("".join(element.itertext()))
        for name, value in element.attrib.items():
            attribute = name.rsplit("}", 1)[-1].lower()
            if attribute.startswith("on"):
                raise ValueError("SVG 不允许事件脚本：" + attribute)
            if attribute in ("href", "src"):
                permitted = value.startswith("#") or re.match(r"^data:image/(png|jpeg|gif|webp);base64,", value, re.I)
                if not permitted:
                    raise ValueError("SVG 不允许外部脚本、远端图片或本地文件引用。")
            if attribute == "style" or "url(" in value.lower():
                _validate_css(value)
    viewbox = root.get("viewBox")
    if viewbox:
        try:
            values = [float(item) for item in re.split(r"[ ,]+", viewbox.strip())]
        except ValueError as exc:
            raise ValueError("SVG viewBox 必须是四个有限数字。") from exc
        if len(values) != 4 or not all(math.isfinite(value) for value in values):
            raise ValueError("SVG viewBox 必须是四个有限数字。")
        width, height = values[2:]
    else:
        def dimension(name):
            value = root.get(name, "")
            if not re.fullmatch(r"\d+(?:\.\d+)?(?:px)?", value):
                raise ValueError("SVG 必须提供 viewBox 或明确的像素宽高。")
            return float(value.removesuffix("px"))
        width, height = dimension("width"), dimension("height")
    if width <= 0 or height <= 0 or width > MAX_SIDE - 48 or height > MAX_SIDE - 48:
        raise ValueError("图示尺寸必须为正数，且每边不超过 8144 像素。")
    return math.ceil(width), math.ceil(height)


def _sized_svg(text, width, height):
    def replace_root(match):
        root_tag = match.group(0)
        root_tag = re.sub(r"\s(?:width|height)\s*=\s*(['\"]).*?\1", "", root_tag, flags=re.S)
        root_tag = re.sub(r"max-width\s*:[^;'\"]*;?", "", root_tag, flags=re.I)
        if not re.search(r"\sxmlns\s*=", root_tag):
            root_tag = root_tag[:-1] + ' xmlns="' + SVG_NS + '">'
        return root_tag[:-1] + ' width="' + str(width) + '" height="' + str(height) + '">'
    return re.sub(r"<svg\b[^>]*>", replace_root, text, count=1, flags=re.S)


def _preview(svg, width, height, title):
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + CSP + '">'
        '<title>' + html.escape(title) + '</title><style>'
        'html,body{margin:0;background:#fff;width:' + str(width) + 'px;height:' + str(height) + 'px;overflow:hidden;}'
        '#diagram{position:absolute;left:50%;top:24px;transform:translateX(-50%);}svg{display:block;max-width:none!important;}'
        'text{font-family:' + FONT + ';}</style></head><body><div id="diagram">'
        + svg + '</div></body></html>'
    )


def _mermaid_page(source, vendor):
    # JSON 转义避免源文本提前结束内联 script；bundle 原样保留许可证。
    definition = json.dumps(source, ensure_ascii=False).replace("<", "\\u003c")
    library = vendor.replace("</script", "<\\/script")
    variables = {
        "primaryColor": "#edf5fc", "primaryTextColor": "#182226",
        "primaryBorderColor": "#607d94", "lineColor": "#65768a",
        "secondaryColor": "#edf7ec", "tertiaryColor": "#fff4e6",
        "textColor": "#182226", "labelTextColor": "#182226",
        "scaleLabelColor": "#182226", "fontFamily": FONT,
    }
    palette = ["#dcecf7", "#e5f0df", "#fce8d2", "#eee3f3"]
    for index in range(12):
        variables["cScale" + str(index)] = palette[index % len(palette)]
        variables["cScaleLabel" + str(index)] = "#182226"
    config = {
        "startOnLoad": False, "securityLevel": "strict", "theme": "base",
        "fontFamily": FONT, "themeVariables": variables,
        "flowchart": {"htmlLabels": False, "useMaxWidth": False},
        "mindmap": {"useMaxWidth": False},
    }
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + CSP + '">'
        '<meta name="diagram-render-result" content="pending">'
        '<style>body{margin:0;background:#fff;}#diagram{display:inline-block;}svg{max-width:none!important;}'
        'body,text{font-family:' + FONT + ';}</style></head><body><div id="diagram"></div>'
        '<script>' + library + '</script><script>'
        'const definition=' + definition + ';'
        'function finish(result){const bytes=new TextEncoder().encode(JSON.stringify(result));'
        'let raw="";for(let i=0;i<bytes.length;i++)raw+=String.fromCharCode(bytes[i]);'
        'document.querySelector("meta[name=diagram-render-result]").content=btoa(raw);}'
        '(async()=>{try{'
        'mermaid.initialize(' + json.dumps(config) + ');'
        'await document.fonts.ready;await mermaid.parse(definition);'
        'const result=await mermaid.render("generated_diagram",definition);'
        'document.getElementById("diagram").innerHTML=result.svg;'
        'const svg=document.querySelector("#diagram svg");'
        'if(!svg)throw new Error("Mermaid returned no SVG element");'
        'finish({status:"ready",svg:new XMLSerializer().serializeToString(svg)});'
        '}catch(error){finish({status:"error",error:String(error&&error.message||error)});}})();'
        '</script></body></html>'
    )


def _run_chrome(executable, page, profile, flags, events):
    command = [
        executable, "--headless", "--no-first-run", "--no-default-browser-check",
        "--disable-background-networking", "--disable-component-update",
        "--disable-sync", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
        "--proxy-server=http://127.0.0.1:9", "--proxy-bypass-list=<-loopback>",
        "--host-resolver-rules=MAP * ~NOTFOUND",
        "--user-data-dir=" + str(profile),
    ] + flags + [page.resolve().as_uri()]
    started = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    timed_out = False
    capture_complete = False
    screenshot_path = next((Path(flag.split("=", 1)[1]) for flag in flags if flag.startswith("--screenshot=")), None)
    try:
        while True:
            remaining = TIMEOUT_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                timed_out = True
                break
            try:
                stdout, stderr = process.communicate(timeout=min(0.3, remaining))
                break
            except subprocess.TimeoutExpired as exc:
                partial = exc.output or b""
                dom_complete = "--dump-dom" in flags and partial.rstrip().endswith(b"</html>")
                if dom_complete or (screenshot_path and _complete_png(screenshot_path)):
                    capture_complete = True
                    break
        # 某些 macOS Chrome 在已输出 DOM/PNG 后持续驻留；确认完整产物再主动退出。
        if capture_complete or timed_out:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
    except BaseException:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        raise
    events.append({
        "stage": "chrome", "command": command, "returncode": process.returncode,
        "duration_seconds": round(time.monotonic() - started, 3), "timeout": timed_out,
        "cleanup_after_complete_output": capture_complete,
        "stdout_bytes": len(stdout), "stderr": stderr.decode("utf-8", errors="replace")[-8000:],
        "network": "denied by isolated proxy, DNS rules and page CSP",
    })
    if timed_out:
        raise ValueError("Chrome 渲染超时（" + str(TIMEOUT_SECONDS) + " 秒），已停止进程组。")
    if process.returncode and not capture_complete:
        raise ValueError("Chrome 退出失败，代码 " + str(process.returncode) + "；详见日志。")
    return stdout.decode("utf-8", errors="replace")


def _png_dimensions(path):
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError("Chrome 未生成有效 PNG。")
    return struct.unpack(">II", header[16:24])


def _complete_png(path):
    try:
        _png_dimensions(path)
        with path.open("rb") as handle:
            handle.seek(-12, os.SEEK_END)
            return handle.read() == b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
    except (OSError, ValueError):
        return False


def render_diagram(input_path, kind, output_dir, stem=None):
    """成功返回产物路径与像素尺寸；失败抛 DiagramRenderError 并留下 JSON 日志。"""
    source_path = Path(input_path).expanduser().resolve()
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    name = stem or source_path.stem
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError("stem 必须是单个文件名，不能包含目录。")
    log_path = directory / (name + ".render.json")
    if log_path.exists() or log_path.is_symlink():
        log_path = directory / (name + ".attempt-" + str(time.time_ns()) + ".render.json")
    events = []
    log = {
        "started_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        "input": str(source_path), "kind": kind, "status": "running", "events": events,
        "visual_verified": False,
    }
    try:
        normalized_kind = {"mmd": "mermaid", "flowchart": "mermaid", "mindmap": "mermaid"}.get(kind, kind)
        if normalized_kind not in ("mermaid", "svg"):
            raise ValueError("kind 仅支持 mermaid（或 mmd/flowchart/mindmap）与 svg。")
        if source_path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("图示源文件超过 256 KB，请拆分图示。")
        source = source_path.read_text(encoding="utf-8-sig")
        if not source.strip():
            raise ValueError("图示源文件为空。")
        source_target = directory / (name + (".mmd" if normalized_kind == "mermaid" else ".source.svg"))
        svg_path = directory / (name + ".svg")
        if svg_path.resolve() == source_path:
            svg_path = directory / (name + ".rendered.svg")
        png_path = directory / (name + ".png")
        preview_path = directory / (name + ".html")
        for path in {source_target, svg_path, png_path, preview_path}:
            if (path.exists() or path.is_symlink()) and path.resolve() != source_path:
                raise ValueError("产物已存在，拒绝覆盖：" + str(path))
        if source_target.resolve() != source_path:
            source_target.write_text(source, encoding="utf-8")
        executable = _chrome_path()
        log["chrome"] = executable
        with tempfile.TemporaryDirectory(prefix="ai-learning-diagram-") as temporary:
            temp = Path(temporary)
            if normalized_kind == "mermaid":
                if REMOTE_URL.search(source) or "%%{" in source:
                    raise ValueError("离线 Mermaid 不允许外部资源 URL 或覆盖配置的初始化指令。")
                vendor_bytes = VENDOR_PATH.read_bytes()
                expected = VENDOR_PATH.with_name("mermaid.sha256").read_text().split()[0]
                digest = hashlib.sha256(vendor_bytes).hexdigest()
                if digest != expected:
                    raise ValueError("本地 Mermaid 文件与随包 SHA-256 不一致。")
                log["mermaid_sha256"] = digest
                mermaid_page = temp / "mermaid.html"
                mermaid_page.write_text(_mermaid_page(source, vendor_bytes.decode("utf-8")), encoding="utf-8")
                dom = _run_chrome(executable, mermaid_page, temp / "parse-profile", [
                    "--virtual-time-budget=10000", "--dump-dom", "--window-size=1600,1200",
                ], events)
                parser = _ResultParser()
                parser.feed(dom)
                try:
                    payload = json.loads(base64.b64decode(parser.payload or "", validate=True))
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    raise ValueError("Mermaid 没有返回明确 ready 状态；详见 Chrome 日志。") from exc
                if payload.get("status") != "ready":
                    raise ValueError("Mermaid 语法或渲染失败：" + str(payload.get("error", "未知错误")))
                svg = payload["svg"]
                events.append({"stage": "mermaid", "status": "ready", "svg_bytes": len(svg.encode("utf-8"))})
            else:
                svg = source
            diagram_width, diagram_height = _validate_svg(svg)
            svg = _sized_svg(svg, diagram_width, diagram_height)
            width, height = max(640, diagram_width + 48), max(240, diagram_height + 48)
            if width * height > MAX_PIXELS:
                raise ValueError("PNG 超过 3200 万像素，请拆分图示。")
            svg_path.write_text(svg, encoding="utf-8")
            preview_path.write_text(_preview(svg, width, height, name), encoding="utf-8")
            events.append({"stage": "svg", "status": "validated", "width": diagram_width, "height": diagram_height})
            _run_chrome(executable, preview_path, temp / "png-profile", [
                "--virtual-time-budget=1000", "--window-size=" + str(width) + "," + str(height),
                "--screenshot=" + str(png_path),
            ], events)
            if not _complete_png(png_path):
                raise ValueError("PNG 文件尚未完整写入，不能标记渲染成功。")
            actual_width, actual_height = _png_dimensions(png_path)
            if (actual_width, actual_height) != (width, height):
                raise ValueError("PNG 尺寸与图示画布不一致：" + str((actual_width, actual_height)))
        result = {
            "source": str(source_target), "svg": str(svg_path), "png": str(png_path),
            "preview": str(preview_path), "log": str(log_path), "width": width, "height": height,
            "status": "rendered", "visual_verified": False,
        }
        log.update(result)
        events.append({"stage": "png", "status": "validated", "bytes": png_path.stat().st_size})
        return result
    except Exception as exc:
        result = {
            "source": str(source_path), "log": str(log_path), "status": "failed",
            "error": str(exc), "visual_verified": False,
        }
        log.update(result)
        raise DiagramRenderError(str(exc), result) from exc
    finally:
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="离线渲染 Mermaid/SVG 为 SVG、PNG 和 HTML 预览。")
    parser.add_argument("input", help="UTF-8 .mmd 或 .svg 源文件")
    parser.add_argument("--kind", choices=["mermaid", "svg", "mmd", "flowchart", "mindmap"], required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--stem")
    args = parser.parse_args(argv)
    try:
        result = render_diagram(args.input, args.kind, args.output_dir, args.stem)
        code = 0
    except DiagramRenderError as exc:
        result, code = exc.result, 1
    except (ValueError, OSError) as exc:
        result, code = {"status": "failed", "error": str(exc), "visual_verified": False}, 1
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
