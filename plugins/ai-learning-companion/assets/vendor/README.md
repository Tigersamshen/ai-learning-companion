# 本地图示依赖

`mermaid.min.js` 原样复制自工作区的 `大模型能力测试集设计方案/_shared/js/mermaid.min.js`，不从 CDN 加载，也不在运行时安装依赖。

- 大小：2,571,900 字节。
- SHA-256：`a43bc1afd446f9c4cc66ac5dd45d02e8d65e26fc5344ec0ef787f88d6ddb6f9e`，同目录 `mermaid.sha256` 供渲染器校验。
- bundle 确切版本尚未可靠识别；以文件摘要锁定，不把上游当前版本当成本地版本。
- `BUNDLED-LICENSES.txt` 保留该文件自身的 bundled license 信息，JS 原文件也保留原注释。
- `MERMAID-LICENSE.txt` 为 [Mermaid 上游 MIT 许可证](https://github.com/mermaid-js/mermaid/blob/develop/LICENSE)（2026-10-09 获取）。

运行时还需要本机 Chrome。渲染器只用 Python 标准库，Chrome 使用临时 profile 和禁止 HTTP/HTTPS 访问的独立参数；预览 HTML 只包含静态 SVG、内联样式和系统字体。
