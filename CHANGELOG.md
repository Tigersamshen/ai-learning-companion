# Changelog

## 0.2.0 — 2026-10-09

- 提供可独立分发的本地 Codex 插件包，包含 `setup.py` 和 macOS 双击入口 `Install.command`。
- 使用独立的 `ai-learning-companion` 市场及相对插件路径，支持 ZIP 交付或有权访问的 GitHub 仓库；保留已有个人市场。
- 将个人学习数据与机器状态置于发布包之外，默认目录为 `~/Documents/AI学习助手`；外部配置默认位于 `~/Library/Application Support/ai-learning-companion/config.json`。
- 支持安装时指定数据目录，并通过 `AI_LEARNING_ROOT`、`AI_LEARNING_CONFIG` 或工具 `--root` 指定运行配置。
- 随包提供初始 Obsidian 笔记模板；接收者通过 Obsidian 界面打开自己的库后登记，不分发原使用者的库 ID、状态、日志或学习记录。
- 保留显式 teach 入口、首次诊断预算、待答题恢复、正式作答与 HTML 练习区分、证据记录和图示视觉验证规则。
- 保留固定上游提交、MIT 通知、本地 Mermaid 文件摘要与 bundled license 通知。

当前安装流程面向 macOS；Windows、Linux 尚未验证。安装检查、自动测试和实际宿主验证分别判断，不能以其中一项替代全部流程。

## 0.1.0

本机初始版本：整合 teach、learn-notes、learn-visualize，提供主题状态、作答记录、Obsidian 同步及本地图示渲染。该版本的配置与数据布局用于原工作区，尚非可移植分发包。
