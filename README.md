# AI 学习助手 · 0.2.0

在 Codex 中确定目标、诊断基础、学习和作答，在 Obsidian 中保存来源、知识依赖图和可追溯的理解记录。适合围绕一个具体目标持续学习，例如“能向同事解释 LLM 的推理过程，并判断哪些输出需要核实”。

这是本地 Codex 插件。学习数据保存在插件包之外；升级插件时可以继续使用已有主题。

## 安装前准备

目前提供 macOS 安装流程。Windows、Linux 尚未验证。

- Python 3.10 或更新版本；在终端运行 `python3 --version` 可检查。
- 你自己的 Codex，已登录可用账户；终端应能运行 `codex plugin --help`。
- 本机 Google Chrome，用于渲染 Mermaid 和 SVG 图示。
- Obsidian，并在其设置中启用**官方 CLI**。无需安装第三方 Obsidian 插件。

Python 工具只使用标准库，Mermaid 资源随包提供。无需 `pip install`、独立 API key 或额外 MCP 服务。学习对话使用你的 Codex；搜索学习资料仍可能需要网络。

## 安装

1. 获取完整 ZIP 并解压，或克隆你有权访问的 GitHub 仓库。私有仓库需要访问权限；直接分享 ZIP 也可以安装。
2. 将解压后的整个 `ai-learning-companion/` 文件夹放到一个长期保留的位置。
3. 双击其中的 **Install.command**。安装器使用默认数据目录，并在终端显示结果。入口会优先使用受支持的 Python；若系统 Python 版本较旧，会查找已安装的新版 Python 或 Codex 随附运行时，不修改系统 Python。
4. 在 Obsidian 中选择“打开文件夹作为库”，打开 `~/Documents/AI学习助手/学习笔记库`。这里的 `~` 表示你的用户主目录。
5. 回到发布包目录，在终端执行：

   ```sh
   python3 setup.py --register-vault
   python3 setup.py --check
   ```

`--register-vault` 读取你通过 Obsidian 界面登记的库；不能替代上面的“打开文件夹作为库”步骤。`--check` 是只读检查：`ok: true` 表示检查执行完成，还要查看各依赖的结果与 `vault.ready`。确认所需功能已就绪后，在 Codex 打开一个新聊天，从技能选择器中确认能找到 `teach`、`learn-notes` 和 `learn-visualize`。

如果希望自己控制安装目录，在发布包目录运行以下命令，替代双击步骤：

```sh
python3 setup.py --data-root "$HOME/Documents/我的学习助手" --install
```

随后在 Obsidian 打开该目录下的 `学习笔记库/`，再执行 `python3 setup.py --register-vault` 和 `python3 setup.py --check`。请不要把数据目录设在发布包或插件缓存内。

安装器会调用 Codex 的官方插件命令：

```sh
codex plugin marketplace add "$PWD"
codex plugin add ai-learning-companion@ai-learning-companion --json
```

发布包使用独立的 `ai-learning-companion` 市场，插件来源为 `./plugins/ai-learning-companion`。它不会覆盖你的 `personal` 市场目录。保留发布包是为了让本地市场来源持续可用。

## 开始第一个主题

正式教学必须显式调用 **`$ai-learning-companion:teach`**。安装插件本身不会启动课程。

先在发布包目录创建主题；标题、目标和成功标准请换成自己的实际需要：

```sh
python3 plugins/ai-learning-companion/scripts/learning_tools.py topic-init \
  --id llm-basics \
  --title "LLM 入门" \
  --mission "向同事解释 LLM 基本推理过程及常见错误，改善工作中的使用判断" \
  --success "能独立解释基本过程，并用一个例子指出输出需要核实的原因"
```

命令返回 JSON，其中的 **`workspace` 是本次主题的真实绝对路径**。在 Codex 中把该目录打开为工作区，然后发送：

> 使用 $ai-learning-companion:teach 开始这个主题。我每天约有 15 分钟；请先了解我已有的基础，再安排第一节短课。

也可以在已有 Codex 工作区中显式调用 teach，同时提供目标主题的真实绝对路径。终端里执行 `cd` 不会改变 Codex 聊天的工作区；不要只提供示例路径或另一个主题的路径。

每个主题保存自己的目标、来源、路线与状态。同一个主题 ID 再次初始化不会覆盖原目标。

## 学习、暂停与继续

- **首次诊断**只检查第一节课程依赖的基础，一次一题，最多六题。可以主动缩短或跳过。全对只确认已测范围的下界；未测内容保持未确认。
- **正式作答在 Codex 完成。**助手先保存题面和选项顺序，再等待你回答。可以答选项 ID、显示的编号、开放题解释，或直接说“不知道”“取消”。
- **续学先恢复状态。**在同一主题工作区显式调用 teach，并说“继续这个主题，先检查上次进度和是否有待答题”。有待答题时恢复原题和原顺序；有待评阅开放题时先完成评阅。
- **旧主题不重做完整诊断。**需要检查相关前置知识时做少量局部复习；目标变化只更新受影响的路线分支，完全无关的目标另建主题。

客观题按稳定选项 ID 判分。开放题由当前 LLM 按原评分标准评阅，记录依据与评阅者；这种评阅仍有模型判断的局限。

HTML 课程中的小测是即时练习，不自动导入正式作答。打开页面、看完课程或点击练习都不等于已理解。`learning-records/` 保存有证据的理解变化、自述先验、纠错或目标变化；`sessions/` 保存学习过程。知识路线的 `confirmed` 必须关联有效理解或纠错证据，自述已有知识不能单独证明掌握。

图示须实际渲染并查看 PNG 后才可标记视觉检查通过。无法渲染或看图时，助手应说明尚未验证。复习由你手动发起，本插件不创建定时提醒。

| 技能 | 用途 |
| --- | --- |
| `$ai-learning-companion:teach` | 新主题诊断、知识路线、短课教学、正式作答和续学 |
| `$ai-learning-companion:learn-notes` | 检查进度、恢复待答题、整理证据、审核同步冲突 |
| `$ai-learning-companion:learn-visualize` | 生成并核对 Mermaid 关系图和 SVG 几何图 |

完整工具参数见 [工具接口](plugins/ai-learning-companion/references/tool-interface.md)，正式作答规则见 [作答协议](plugins/ai-learning-companion/references/quiz-protocol.md)。

## 文件、配置与备份

发布包的目录结构：

```text
ai-learning-companion/
├── Install.command
├── setup.py
├── .agents/plugins/marketplace.json
├── plugins/ai-learning-companion/
│   ├── skills/ · agents/ · references/ · scripts/
│   └── assets/templates/learning-vault/   初始笔记模板
└── tests/                               工具验证
```

默认个人数据与配置：

```text
~/Documents/AI学习助手/
├── 学习笔记库/主题/<topic-id>/            目标、来源、课程、图示与记录
├── state/                               待答题、进度与同步冲突
└── deployment.json                      本机 Obsidian 库登记

~/Library/Application Support/ai-learning-companion/config.json
```

`AI_LEARNING_ROOT` 可以指定数据目录，`AI_LEARNING_CONFIG` 可以指定外部配置文件；单次工具调用也可使用 `--root <数据目录>`。自定义安装后，应让相关命令使用同一数据目录，避免在另一位置创建空主题。

备份**整个个人数据目录**，包括 `学习笔记库/`、`state/` 和 `deployment.json`，并保存外部配置。只备份 Obsidian 库会遗漏待答题等机器状态。迁移后在 Obsidian 打开新位置的库，重新运行安装器设置数据目录与 `--register-vault`，再检查主题状态。

你可以手工编辑笔记。同步发现冲突会保留原稿，将候选合并内容写到 `state/conflicts/`。在 Codex 显式使用 learn-notes 审核两版并合并；不要删除原稿或强制重生成。手改 `MISSION.md` 的目标后，还应在 Codex 明确说明新目标，让助手更新工具状态。

## 常见问题

| 现象 | 检查与处理 |
| --- | --- |
| 双击 Install.command 没启动 | 在发布包目录执行 `python3 setup.py --install`；若只是执行权限缺失，可执行 `chmod +x Install.command` 后重试。 |
| 找不到 `python3` 或版本低于 3.10 | 安装或选择 Python 3.10+，确认终端的 `python3 --version`，再运行安装。 |
| 找不到 `codex` 或没有 `plugin` 子命令 | 先让你自己的 Codex CLI 在终端可用，并确认 `codex plugin --help` 可运行。 |
| Codex 技能选择器没有 teach | 运行 `python3 setup.py --check`，核对安装结果；重新打开 Codex 并新建聊天。显式名称是 `$ai-learning-companion:teach`。 |
| Vault 未登记、打不开笔记 | 先在 Obsidian 界面打开实际数据目录下的 `学习笔记库/`，启用官方 CLI，保持 Obsidian 运行，再执行 `python3 setup.py --register-vault`。 |
| CLI 报找不到 Obsidian | 同时检查应用是否运行、官方 CLI 是否启用。IPC 或权限失败不一定表示应用未安装。 |
| 图示无法渲染 | 检查 Chrome 是否安装，保留返回的具体错误；Codex 沙箱可能限制进程启动，应按宿主的正常权限流程重试。不要关闭 Chrome 的进程沙箱。 |
| 显示笔记同步冲突 | 使用 learn-notes 查看原稿和候选内容，审核后合并；原稿会保留。 |
| 续学看不到原进度 | 检查工作区、配置和 `AI_LEARNING_ROOT` 是否指向原主题的数据目录，先恢复状态再学习。 |

本版已通过 50 项测试，包括真实 Chrome 渲染与 10 项安装器测试；ZIP 已在全新临时目录中解压、初始化、创建主题并核对内部文件摘要。官方 Codex 安装命令还单独做了真实安装及清理验证。新用户仍需在自己的 Obsidian 界面打开笔记库并登记。测试使用临时数据，不能作为学习者理解或掌握情况的证据。

## 来源与许可

- 学习流程的启发：[Amos Blomqvist 的视频](https://youtu.be/kzcI5F4tGiU)及其 [learn 仓库](https://github.com/amosblomqvist/learn)。该仓库的代码和技能文本未打包；有关脑机制的个人解释不作为已确立的科学定律。
- teach 基线：[Matt Pocock 的 teach](https://github.com/mattpocock/skills/tree/b0618bc436ad893b3c5e84e55fba86586d34a404/skills/productivity/teach)，固定提交 `b0618bc436ad893b3c5e84e55fba86586d34a404`。知识、技能、智慧框架和四份格式模板保留；本地适配详见 [UPSTREAM.md](plugins/ai-learning-companion/UPSTREAM.md)。
- 原 MIT 通知保留在 [插件 LICENSE](plugins/ai-learning-companion/LICENSE)。本地 Mermaid 文件以 SHA-256 固定，原 bundled license 通知保留在 [BUNDLED-LICENSES.txt](plugins/ai-learning-companion/assets/vendor/BUNDLED-LICENSES.txt)，另附 [Mermaid MIT 通知](plugins/ai-learning-companion/assets/vendor/MERMAID-LICENSE.txt)。分享 ZIP 或重新分发时请保留这些文件。

版本变化见 [CHANGELOG.md](CHANGELOG.md)。
